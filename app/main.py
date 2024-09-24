"""
Это приложение на FastAPI предназначено для сбора, хранения и отображения игровых данных от различных игроков.
Оно использует WebSocket для обеспечения обновлений данных в реальном времени, позволяя пользователям видеть изменения немедленно
без необходимости обновления страницы.

Основные компоненты приложения:

1. Модели данных: Приложение использует SQLAlchemy для работы с базой данных SQLite. Мы определили модель PlayerData,
   которая представляет структуру таблицы в базе данных для хранения данных игроков (имя, текст диалога, тип данных, временная метка).

2. Маршруты:
   - Главная страница ("/"): Отображает список всех игроков. Устанавливается WebSocket соединение для получения обновлений о новых игроках.
   - Страница данных игрока ("/player/{player_name}"): Отображает детали конкретного игрока, включая его диалоги и временные метки.

3. WebSocket соединения: Поддерживает мгновенные обновления. Когда данные игрока отправляются через WebSocket, 
   они автоматически обновляют информацию у всех подключенных пользователей.

4. CSS стили и интерфейс: Включает подключенные стили для улучшения визуального восприятия и создания дружелюбного интерфейса.

Как это работает:
1. При запуске приложения создается база данных и таблицы для хранения данных о игроках.
2. Пользователь открывает главную страницу, где отображается список всех игроков и устанавливается WebSocket соединение.
3. При выборе игрока пользователь перенаправляется на страницу с его данными, где видна его история действий.
4. Новые данные, поступающие для любого игрока, мгновенно отображаются у всех подключенных пользователей благодаря WebSocket.

Пример запроса:
1. Для добавления новых данных о игроке отправьте POST запрос на URL /player_data с JSON телом запроса:

   URL: POST http://localhost:8000/player_data
   Заголовки:
   Content-Type: application/json

   Тело запроса:
   {
       "player_name": "Игрок1",
       "dialog_text": "Это текст диалога",
       "data_type": "диалог"
   }

   Примечание: В этом примере мы отправляем имя игрока, текст диалога и тип данных. Эти данные будут добавлены в базу данных.

2. Для получения данных о конкретном игроке выполните GET запрос на URL /player/{player_name}:

   URL: GET http://localhost:8000/player/Игрок1

   Примечание: Этот запрос вернет все данные, связанные с игроком "Игрок1", включая текст диалога и временные метки.
"""

# Импорт необходимых библиотек из FastAPI и других модулей
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from datetime import datetime
import json
from typing import List, Dict
from contextlib import contextmanager
import pytz

# Создание экземпляра приложения FastAPI
app = FastAPI()

# Подключение статических файлов (например, CSS) из директории "static"
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="static"), name="static")

# Определение URL для базы данных SQLite
DATABASE_URL = "sqlite:///./game_data.db"
engine = create_engine(DATABASE_URL)  # Создание движка базы данных
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)  # Фабрика сессий для базы данных
session_factory = scoped_session(SessionLocal)  # Обеспечение потокобезопасной сессии
Base = declarative_base()  # Создание базового класса для моделей

# Определение модели данных для игрока
class PlayerData(Base):
    __tablename__ = "player_data"  # Имя таблицы в базе данных
    id = Column(Integer, primary_key=True, index=True)  # Первичный ключ
    player_name = Column(String(50), index=True)  # Имя игрока
    dialog_text = Column(Text)  # Текст диалога
    data_type = Column(String(50))  # Тип данных (например, "диалог", "ввод" и т.д.)
    timestamp = Column(DateTime, default=datetime.utcnow)  # Время создания записи

# Создание всех таблиц в базе данных
Base.metadata.create_all(bind=engine)

# Определение модели для входящих данных
class PlayerDataIn(BaseModel):
    player_name: str  # Имя игрока
    dialog_text: str  # Текст диалога
    data_type: str  # Тип данных

# Контекстный менеджер для работы с базой данных
@contextmanager
def get_db():
    db = session_factory()  # Создание новой сессии
    try:
        yield db  # Возврат сессии
    finally:
        db.close()  # Закрытие сессии после использования

# Менеджер для работы с WebSocket соединениями
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[WebSocket, str] = {}  # Хранение активных соединений

    async def connect(self, websocket: WebSocket, data_type: str):
        await websocket.accept()  # Принятие WebSocket соединения
        self.active_connections[websocket] = data_type  # Сохранение соединения и типа данных

    def disconnect(self, websocket: WebSocket):
        # Удаление соединения из активных
        if websocket in self.active_connections:
            del self.active_connections[websocket]

    async def broadcast(self, message: str, data_type: str):
        # Отправка сообщения всем подключенным WebSocket соединениям
        for connection, conn_data_type in self.active_connections.items():
            if conn_data_type == 'all' or conn_data_type == data_type:
                await connection.send_text(message)  # Отправка сообщения

manager = ConnectionManager()  # Создание экземпляра менеджера соединений

# Маршрут для главной страницы, возвращает HTML-код с игроками
@app.get("/", response_class=HTMLResponse)
async def index():
    with get_db() as session:
        players = session.query(PlayerData.player_name).distinct().all()  # Получение уникальных имен игроков
    players = [player[0] for player in players]  # Преобразование списка к удобному формату
    return f"""
    <html lang="ru">
    <head>
        <title>Игровые данные</title>
        <link rel="stylesheet" href="/static/style.css">  # Подключение стилей
        <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">  # Подключение шрифтов
        <script>
            let socket = new WebSocket("ws://localhost:8000/ws?data_type=all");  # Установка WebSocket соединения

            socket.onmessage = function(event) {{
                const data = JSON.parse(event.data);  # Обработка входящих сообщений
                if (data.players) {{
                    updatePlayerList(data.players);  # Обновление списка игроков
                }}
            }};
            
            function updatePlayerList(players) {{
                const playerList = document.querySelector(".player-list");
                playerList.innerHTML = players.map(player => 
                    `<div class="player-item"><a href="/player/${{player}}">${{player}}</a></div>`
                ).join('');  # Обновление HTML списка игроков
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

# Маршрут для отображения данных конкретного игрока
@app.get("/player/{player_name}", response_class=HTMLResponse)
async def player_data(player_name: str, data_type: str = 'all'):
    with get_db() as session:
        # Запрос данных игрока в зависимости от типа
        if data_type == 'all':
            player_data = session.query(PlayerData).filter_by(player_name=player_name).order_by(PlayerData.timestamp.desc()).all()
        else:
            player_data = session.query(PlayerData).filter_by(player_name=player_name, data_type=data_type).order_by(PlayerData.timestamp.desc()).all()
    
        # Словарь для отображения названий месяцев на русском
        month_names = {
            1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
            7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
        }

        player_data_html = ""  # HTML-код для отображения данных игрока
        last_date = None  # Переменная для отслеживания последней даты
        current_table_html = ""  # HTML-код для текущей таблицы данных

        moscow_tz = pytz.timezone('Europe/Moscow')  # Установка часового пояса

        # Обработка данных игрока
        for data in player_data:
            moscow_time = data.timestamp.astimezone(moscow_tz)  # Приведение времени к московскому
            date_str = moscow_time.strftime('%d %m %Y')  # Форматирование даты
            day, month, year = date_str.split()  # Разделение даты на части
            month_russian = month_names[int(month)]  # Получение названия месяца на русском
            formatted_date = f"{day} {month_russian} {year} года"  # Форматирование даты для отображения
            time_str = moscow_time.strftime('%H:%M:%S')  # Форматирование времени

            # Проверка на изменение даты для отображения
            if last_date != formatted_date:
                if current_table_html:
                    player_data_html += f"""
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Время</th>
                                <th>Текст</th>
                            </tr>
                        </thead>
                        <tbody>
                            {current_table_html}  # Добавление текущей таблицы в HTML
                        </tbody>
                    </table>
                    </div>"""

                player_data_html += f"""
                <div class="date-section">
                    <h2 class="date-header">{formatted_date}</h2>  # Заголовок с датой
                """
                current_table_html = ""  # Сброс текущей таблицы
                last_date = formatted_date  # Обновление последней даты

            current_table_html += f"""
            <tr>
                <td class="time">{time_str}</td>  # Отображение времени
                <td class="dialog-text">{data.dialog_text}</td>  # Отображение текста диалога
            </tr>"""

        # Добавление оставшейся таблицы, если она есть
        if current_table_html:
            player_data_html += f"""
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Время</th>
                        <th>Текст</th>
                    </tr>
                </thead>
                <tbody>
                    {current_table_html}
                </tbody>
            </table>
            </div>"""

    return f"""
    <html lang="ru">
    <head>
        <title>Данные игрока: {player_name}</title>
        <link rel="stylesheet" href="/static/style.css">  # Подключение стилей
        <script>
            let socket = new WebSocket("ws://localhost:8000/ws?data_type={data_type}");  # Установка WebSocket соединения
        </script>
    </head>
    <body>
        <div class="container">
            <h1>Данные игрока: {player_name}</h1>
            {player_data_html}  # Отображение данных игрока
        </div>
    </body>
    </html>
    """

# Маршрут для обработки WebSocket соединений
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    data_type = websocket.query_params.get("data_type")  # Получение типа данных из параметров запроса
    await manager.connect(websocket, data_type)  # Подключение WebSocket

    try:
        while True:
            data = await websocket.receive_text()  # Ожидание получения текста
            data_dict = json.loads(data)  # Преобразование строки в словарь
            player_data = PlayerData(**data_dict)  # Создание объекта PlayerData
            with get_db() as session:
                session.add(player_data)  # Добавление данных в сессию
                session.commit()  # Коммит изменений
            await manager.broadcast(data, data_type)  # Рассылка данных всем подключенным пользователям
    except WebSocketDisconnect:
        manager.disconnect(websocket)  # Отключение WebSocket
        await manager.broadcast(json.dumps({"message": "Пользователь отключился."}), data_type)  # Рассылка сообщения об отключении

# Запуск приложения с uvicorn
# Команда для запуска: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)