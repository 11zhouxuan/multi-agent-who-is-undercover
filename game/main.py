import json
import threading
import asyncio
from typing import Dict
import logging.config
from fastapi import APIRouter, WebSocket , WebSocketDisconnect
from common import constant
from common.enum import ContentType, GameStatus
from . import schemas
from .my_exception import ResetException
from who_is_undercover_backend import WhoIsUndercover,Player

logging.config.fileConfig('logging.conf', disable_existing_loggers=False)
logger = logging.getLogger(constant.LOGGER_API)
router = APIRouter(prefix="/game", tags=["game"])

websockets: Dict[str, WebSocket] = {}
status = GameStatus.STOPED
reset_event = threading.Event()
pause_event = threading.Event()
game_obj: WhoIsUndercover = None
vote_event = threading.Event()
prefer_words: list[str] = []
second_agent_prefer_words: str = None


@router.get("/china-ware-words", response_model=list[schemas.ChinaWareWord])
def china_ware_words() -> list[schemas.ChinaWareWord]:
    return constant.CHINAWARE_WORDS_LIST


@router.post("/begin", response_model=schemas.CommonResponse)
def begin(game: schemas.Game) -> schemas.CommonResponse:
    logger.info(game)

    global status
    if status != GameStatus.STOPED:
        return schemas.CommonResponse(message="Error")

    status = GameStatus.RUNNING
    reset_event.clear()
    pause_event.clear()

    try:
        global game_obj
        game_obj = WhoIsUndercover(
            is_about_chinaware=game.is_about_chinaware,
            common_word=game.common_word,
            undercover_word=game.undercover_word,
            player_num=6,
            llm_model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            stream=True,
        )
        vote_event.clear()
        global prefer_words
        prefer_words = game.prefer_words
        global second_agent_prefer_words
        second_agent_prefer_words = None

        broadcast(ContentType.GAME_BEGIN)

        while not game_obj.is_game_close():
            next_turn()
    except ResetException:
        reset_event.set()
        logger.info("发送reset")
        status = GameStatus.STOPED
        broadcast(ContentType.GAME_RESET)

    return schemas.CommonResponse(message="OK")


def __check_pause():
    if status == GameStatus.PAUSED:
        logger.info("进入暂停")
        pause_event.wait()
        if pause_event.is_set():
            logger.info("游戏继续")
        else:
            logger.info("游戏超时继续")


def next_turn():
    __speak()
    __vote()
    __check_game_end()


def __speak():
    logger.info(f"第{game_obj.current_turn}轮陈述开始")
    broadcast(ContentType.TURN_SPEAK_BEGIN, {"TurnNumber":game_obj.current_turn})

    for player_statement in game_obj.next_turn_statement():
        player:Player = player_statement['player']
        if player.active:
            logger.info(f'Player {player.player_id} 开始陈述。')
        else:
            continue
        broadcast(ContentType.AGENT_SPEAK_BEGIN,{"SpeakAgentId":player.player_id})

        his = player.history[-1]
        if game_obj.stream:
            logger.info("**Thinking:**")
            unicast(player.player_id, ContentType.AGENT_SPEAK_THINKING, f"**Thinking:**")
            for current_thinking in his['thinking']:
                unicast(player.player_id, ContentType.AGENT_SPEAK_THINKING, current_thinking)
            logger.info("**statement:**")
            # unicast(player.player_id, ContentType.AGENT_SPEAK, f"**Speak:**")
            s = ""
            for current_statement in his['statement']:
                s += current_statement
                # unicast(player.player_id, ContentType.AGENT_SPEAK, current_statement)
            unicast(player.player_id, ContentType.AGENT_SPEAK, s)
        else:
            logger.info(f"**Thinking:** {his['thinking']}")
            logger.info(his['statement'])
            unicast(player.player_id, ContentType.AGENT_SPEAK_THINKING, f"**Thinking:** {his['thinking']}")
            unicast(player.player_id, ContentType.AGENT_SPEAK, his['statement'])
        broadcast(ContentType.AGENT_SPEAK_END,{"SpeakAgentId":player.player_id})

        __check_pause()

        # 第1轮设置Agent2的思考方向
        if game_obj.is_about_chinaware and game_obj.current_turn == 1 and player.player_id == "1":
            broadcast(ContentType.AGENT_SPEAK_CHOOSE, prefer_words)

            logger.info("等待选择")
            vote_event.wait(timeout=20)
            if vote_event.is_set():
                logger.info(f"接收到{second_agent_prefer_words}")
                game_obj.second_agent_prefer_words = second_agent_prefer_words
            else:
                logger.info("超时设置Agent2思考方向")
                game_obj.second_agent_prefer_words = prefer_words[0]

    broadcast(ContentType.TURN_SPEAK_END, {"TurnNumber":game_obj.current_turn})


def __vote():
    logger.info(f"第{game_obj.current_turn}轮投票开始")
    broadcast(ContentType.TURN_VOTE_BEGIN, {"TurnNumber":game_obj.current_turn})

    for player_vote in game_obj.next_turn_vote():
        player: Player = player_vote['player']
        if player.active:
            logger.info(f'Player {player.player_id} 开始投票。')
        else:
            continue
        broadcast(ContentType.AGENT_VOTE_BEGIN,{"SpeakAgentId":player.player_id})

        his = player.vote_history[-1]
        if game_obj.stream:
            logger.info("**VoteThinking:**")
            unicast(player.player_id, ContentType.AGENT_VOTE_THINKING, f"**VoteThinking:**")
            for current_thinking in his['thinking']:
                unicast(player.player_id, ContentType.AGENT_VOTE_THINKING, current_thinking)
            logger.info("**Vote:**")
            # unicast(player.player_id, ContentType.AGENT_VOTE, f"**Vote:**")
            s = ""
            for current_vote in his['vote']:
                # unicast(player.player_id, ContentType.AGENT_VOTE, current_vote)
                s += current_vote
            unicast(player.player_id, ContentType.AGENT_VOTE, s)
        else:
            logger.info(f"**VoteThinking:** {his['thinking']}")
            logger.info(f'Player {player.player_id} 投票给 Player {his["vote"]}')
            unicast(player.player_id, ContentType.AGENT_VOTE_THINKING, f"**Thinking:** {his['thinking']}")
            unicast(player.player_id, ContentType.AGENT_VOTE, f'投票给 Player {his["vote"]}')
            logger.info(f'Player {player.player_id} 完成投票。')
        broadcast(ContentType.AGENT_VOTE_END,{"SpeakAgentId":player.player_id})

        __check_pause()
        
    out_player = game_obj.execute_vote_result()
    logger.info(f'Player {out_player.player_id} 被投票出局！')
    broadcast(ContentType.TURN_VOTE_END, {"TurnNumber":game_obj.current_turn,"OutAgentId":out_player.player_id})
    
    game_obj.current_turn += 1


def __check_game_end():
    if game_obj.is_game_close():
        logger.info(f'游戏结束')
        logger.info(game_obj.game_status)
        logger.info(f'平民词: {game_obj.common_word}, 卧底词: {game_obj.undercover_word}')
        undercover_player = game_obj.get_undercover_player()
        broadcast(ContentType.GAME_END, {"Status":game_obj.game_status,
                                         "CommonWord":game_obj.common_word,
                                         "UndercoverWord":game_obj.undercover_word,
                                         "UndercoverPlayerId":undercover_player.player_id,
                                         "UndercoverActive":undercover_player.active,
                                        })
        global status
        status = GameStatus.STOPED


@router.post("/second-agent-prefer-words", response_model=schemas.CommonResponse)
def second_agent_prefer_words(prefer_words_in: str) -> schemas.CommonResponse:
    logger.info(f"prefer_words:{prefer_words_in}")
    global second_agent_prefer_words
    second_agent_prefer_words = prefer_words_in
    vote_event.set()
    return schemas.CommonResponse(message="OK")


@router.post("/reset", response_model=schemas.CommonResponse)
def reset() -> schemas.CommonResponse:
    global status
    logger.info(f"Game status:{status.value}")
    if status == GameStatus.RUNNING:
        status = GameStatus.STOPPING
        logger.info("Game stopping")
        reset_event.wait(timeout=20)
        if reset_event.is_set():
            status = GameStatus.STOPED
        else:
            status = GameStatus.STOPED
        logger.info("Game stopped")
    return schemas.CommonResponse(message="OK")


@router.post("/pause", response_model=schemas.CommonResponse)
def pause() -> schemas.CommonResponse:
    global status
    logger.info(f"Game status:{status.value}")
    if status == GameStatus.RUNNING:
        pause_event.clear()
        status = GameStatus.PAUSED
        logger.info("Game paused")
    return schemas.CommonResponse(message="OK")


@router.post("/continue", response_model=schemas.CommonResponse)
def continue_game() -> schemas.CommonResponse:
    global status
    logger.info(f"Game status:{status.value}")
    if status == GameStatus.PAUSED:
        pause_event.set()
        status = GameStatus.RUNNING
        logger.info("Game running")
    return schemas.CommonResponse(message="OK")


@router.websocket("/ws/controller")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    agent_id = "controller"
    websockets[agent_id] = websocket
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"agent_id:{agent_id},data={data}")
            for current_agent_id, current_websocket in websockets.items():
                content_obj = {
                    "agent_id": current_agent_id,
                    "content_type": ContentType.CUSTOM.value,
                    "content": data,
                }
                final_content = json.dumps(content_obj)
                await current_websocket.send_text(final_content)
    except WebSocketDisconnect:
        logger.info(f"agent_id={agent_id},{websocket.client.host}:{websocket.client.port} disconnected.")


@router.websocket("/ws/{agent_id}")
async def websocket_endpoint(websocket: WebSocket, agent_id: str):
    await websocket.accept()
    websockets[agent_id] = websocket
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"agent_id:{agent_id},data={data}")
    except WebSocketDisconnect:
        logger.info(f"agent_id={agent_id},{websocket.client.host}:{websocket.client.port} disconnected.")


def unicast(agent_id: str, content_type: ContentType, content=None):
    if status == GameStatus.STOPPING:
        raise ResetException()
    websocket = websockets[agent_id]
    content_obj = {
        "agent_id": agent_id,
        "content_type": content_type.value,
        "content": content,
    }
    final_content = json.dumps(content_obj)
    asyncio.run(websocket.send_text(final_content))


def broadcast(content_type: ContentType, content=None):
    for agent_id in websockets:
        unicast(agent_id, content_type, content)
