from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from fastapi.responses import HTMLResponse, FileResponse

app = FastAPI()

# Database setup
DATABASE_URL = "sqlite:///./game_data.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Model setup
class PlayerData(Base):
    __tablename__ = "player_data"

    id = Column(Integer, primary_key=True, index=True)
    player_name = Column(String(50), index=True)
    dialog_text = Column(Text)
    data_type = Column(String(50))
    timestamp = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# Pydantic model for input validation
class PlayerDataIn(BaseModel):
    player_name: str
    dialog_text: str
    data_type: str

@app.get("/", response_class=HTMLResponse)
async def index():
    with SessionLocal() as session:
        players = session.query(PlayerData.player_name).distinct().all()
    players = [player[0] for player in players]
    return FileResponse('templates/index.html', media_type='text/html')

@app.get("/player/{player_name}", response_class=HTMLResponse)
async def player_data(player_name: str, data_type: str = 'all'):
    with SessionLocal() as session:
        if data_type == 'all':
            player_data = session.query(PlayerData).filter_by(player_name=player_name).all()
        else:
            player_data = session.query(PlayerData).filter_by(player_name=player_name, data_type=data_type).all()
    
    player_data_html = "".join(f"""
    <tr>
        <td>{data.player_name}</td>
        <td>{data.dialog_text}</td>
        <td>{data.data_type}</td>
        <td>{data.timestamp}</td>
    </tr>""" for data in player_data)
    
    return FileResponse('templates/player_data.html', media_type='text/html')

@app.post("/submit_data")
async def submit_data(data: PlayerDataIn):
    with SessionLocal() as session:
        new_data = PlayerData(
            player_name=data.player_name,
            dialog_text=data.dialog_text,
            data_type=data.data_type
        )
        session.add(new_data)
        session.commit()
    return {"message": "Data saved successfully"}

@app.get("/static/{file_name}")
async def get_static(file_name: str):
    return FileResponse(f'static/{file_name}')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
