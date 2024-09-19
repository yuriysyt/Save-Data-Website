from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import asyncio
import json

app = FastAPI()

# Database setup (оставляем без изменений)
DATABASE_URL = "sqlite:///./game_data.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class PlayerData(Base):
    __tablename__ = "player_data"
    id = Column(Integer, primary_key=True, index=True)
    player_name = Column(String(50), index=True)
    dialog_text = Column(Text)
    data_type = Column(String(50))
    timestamp = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

class PlayerDataIn(BaseModel):
    player_name: str
    dialog_text: str
    data_type: str

# Глобальная переменная для хранения последнего обновления
latest_update = None

@app.get("/", response_class=HTMLResponse)
async def index():
    with SessionLocal() as session:
        players = session.query(PlayerData.player_name).distinct().all()
    players = [player[0] for player in players]
    return f"""
    <html>
    <head>
        <title>Game Data</title>
        <link rel="stylesheet" href="/static/style.css">
        <script>
            const eventSource = new EventSource("/sse");
            eventSource.onmessage = function(event) {{
                const data = JSON.parse(event.data);
                updatePlayerList(data.players);
            }};
            
            function updatePlayerList(players) {{
                const playerList = document.querySelector(".player-list");
                playerList.innerHTML = players.map(player => 
                    `<div class="player-item"><a href="/player/${{player}}">${{player}}</a></div>`
                ).join('');
            }}
        </script>
    </head>
    <body>
        <div class="container">
            <h1>Players</h1>
            <div class="player-list">
            {''.join(f'<div class="player-item"><a href="/player/{player}">{player}</a></div>' for player in players)}
            </div>
        </div>
    </body>
    </html>
    """

@app.get("/player/{player_name}", response_class=HTMLResponse)
async def player_data(player_name: str, data_type: str = 'all'):
    with SessionLocal() as session:
        if data_type == 'all':
            player_data = session.query(PlayerData).filter_by(player_name=player_name).order_by(PlayerData.timestamp.desc()).all()
        else:
            player_data = session.query(PlayerData).filter_by(player_name=player_name, data_type=data_type).order_by(PlayerData.timestamp.desc()).all()
    
    player_data_html = "".join(f"""
    <tr>
        <td class="dialog-text">{data.dialog_text}</td>
        <td>{data.timestamp}</td>
    </tr>""" for data in player_data)
    
    return f"""
    <html>
    <head>
        <title>Data for {player_name}</title>
        <link rel="stylesheet" href="/static/style.css">
        <script>
            const eventSource = new EventSource("/sse");
            eventSource.onmessage = function(event) {{
                const data = JSON.parse(event.data);
                if (data.new_data && data.new_data.player_name === '{player_name}') {{
                    addNewData(data.new_data);
                }}
            }};
            
            function addNewData(newData) {{
                const dataTable = document.querySelector(".data-table tbody");
                if (dataTable) {{
                    const newRow = document.createElement('tr');
                    newRow.innerHTML = `
                        <td class="dialog-text">${{newData.dialog_text}}</td>
                        <td>${{newData.timestamp}}</td>
                    `;
                    dataTable.insertBefore(newRow, dataTable.firstChild);
                }}
            }}
        </script>
    </head>
    <body>
        <div class="container">
            <h1>Data for {player_name}</h1>
            <div class="filters">
                <a href="/player/{player_name}?data_type=all" class="filter-button {'active' if data_type == 'all' else 'inactive'}">All</a>
                <a href="/player/{player_name}?data_type=dialog" class="filter-button {'active' if data_type == 'dialog' else 'inactive'}">Dialog</a>
                <a href="/player/{player_name}?data_type=input" class="filter-button {'active' if data_type == 'input' else 'inactive'}">Input</a>
                <a href="/player/{player_name}?data_type=chat" class="filter-button {'active' if data_type == 'chat' else 'inactive'}">Chat</a>
                <a href="/player/{player_name}?data_type=command" class="filter-button {'active' if data_type == 'command' else 'inactive'}">Command</a>
            </div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Dialog Text</th>
                        <th>Timestamp</th>
                    </tr>
                </thead>
                <tbody>
                    {player_data_html}
                </tbody>
            </table>
            <a href="/" class="back-button">Back to Home</a>
        </div>
    </body>
    </html>
    """

@app.get("/sse")
async def sse(request: Request):
    async def event_generator():
        global latest_update
        while True:
            if await request.is_disconnected():
                break

            if latest_update:
                yield {
                    "data": json.dumps(latest_update)
                }
                latest_update = None

            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())

@app.post("/submit_data")
async def submit_data(data: PlayerDataIn):
    global latest_update
    with SessionLocal() as session:
        new_data = PlayerData(
            player_name=data.player_name,
            dialog_text=data.dialog_text,
            data_type=data.data_type,
            timestamp=datetime.utcnow()
        )
        session.add(new_data)
        session.commit()
        
        # Обновляем latest_update
        players = session.query(PlayerData.player_name).distinct().all()
        players = [player[0] for player in players]
        latest_update = {
            "players": players,
            "new_data": {
                "player_name": new_data.player_name,
                "dialog_text": new_data.dialog_text,
                "data_type": new_data.data_type,
                "timestamp": new_data.timestamp.isoformat()
            }
        }
    
    return {"message": "Data saved successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)