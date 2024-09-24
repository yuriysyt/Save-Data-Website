from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from datetime import datetime
import json
from typing import List
from contextlib import contextmanager

app = FastAPI()
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Serve static files from the 'static' directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Database setup
DATABASE_URL = "sqlite:///./game_data.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
session_factory = scoped_session(SessionLocal)
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

@contextmanager
def get_db():
    db = session_factory()
    try:
        yield db
    finally:
        db.close()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.get("/", response_class=HTMLResponse)
async def index():
    with get_db() as session:
        players = session.query(PlayerData.player_name).distinct().all()
    players = [player[0] for player in players]
    return f"""
    <html lang="ru">
    <head>
        <title>Игровые данные</title>
        <link rel="stylesheet" href="/static/style.css">
        <script>
            let socket = new WebSocket("ws://localhost:8000/ws");
            
            socket.onmessage = function(event) {{
                const data = JSON.parse(event.data);
                if (data.players) {{
                    updatePlayerList(data.players);
                }}
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
            <h1>Игроки</h1>
            <div class="player-list">
            {''.join(f'<div class="player-item"><a href="/player/{player}">{player}</a></div>' for player in players)}
            </div>
        </div>
    </body>
    </html>
    """

@app.get("/player/{player_name}", response_class=HTMLResponse)
async def player_data(player_name: str, data_type: str = 'all'):
    with get_db() as session:
        if data_type == 'all':
            player_data = session.query(PlayerData).filter_by(player_name=player_name).order_by(PlayerData.timestamp.desc()).all()
        else:
            player_data = session.query(PlayerData).filter_by(player_name=player_name, data_type=data_type).order_by(PlayerData.timestamp.desc()).all()
    
        player_data_html = "".join(f"""
        <tr>
            <td class="dialog-text">{data.dialog_text}</td>
            <td>{data.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</td>
        </tr>""" for data in player_data)
    
    return f"""
    <html lang="ru">
    <head>
        <title>Данные для {player_name}</title>
        <link rel="stylesheet" href="/static/style.css">
        <script>
            let socket = new WebSocket("ws://localhost:8000/ws");
            
            socket.onmessage = function(event) {{
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
            <h1>Данные для {player_name}</h1>
            <div class="filters">
                <a href="/player/{player_name}?data_type=all" class="filter-button {'active' if data_type == 'all' else 'inactive'}">Все</a>
                <a href="/player/{player_name}?data_type=dialog" class="filter-button {'active' if data_type == 'dialog' else 'inactive'}">Диалоги</a>
                <a href="/player/{player_name}?data_type=input" class="filter-button {'active' if data_type == 'input' else 'inactive'}">Ввод</a>
                <a href="/player/{player_name}?data_type=chat" class="filter-button {'active' if data_type == 'chat' else 'inactive'}">Чат</a>
                <a href="/player/{player_name}?data_type=command" class="filter-button {'active' if data_type == 'command' else 'inactive'}">Команды</a>
            </div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Текст</th>
                        <th>Время</th>
                    </tr>
                </thead>
                <tbody>
                    {player_data_html}
                </tbody>
            </table>
            <a href="/" class="back-button">Назад к игрокам</a>
        </div>
    </body>
    </html>
    """

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Здесь можно обрабатывать входящие сообщения от клиента, если нужно
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/submit_data")
async def submit_data(data: PlayerDataIn):
    with get_db() as session:
        new_data = PlayerData(
            player_name=data.player_name,
            dialog_text=data.dialog_text,
            data_type=data.data_type,
            timestamp=datetime.utcnow()
        )
        session.add(new_data)
        session.commit()
        
        # Получаем обновленный список игроков
        players = session.query(PlayerData.player_name).distinct().all()
        players = [player[0] for player in players]

        # Создаем словарь с данными нового объекта
        new_data_dict = {
            "player_name": new_data.player_name,
            "dialog_text": new_data.dialog_text,
            "data_type": new_data.data_type,
            "timestamp": new_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }

    # Отправляем обновление всем подключенным клиентам
    await manager.broadcast(json.dumps({
        "players": players,
        "new_data": new_data_dict
    }))
    
    return {"message": "Данные успешно сохранены"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
