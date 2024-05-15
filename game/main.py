import json
import os
import threading
import traceback
import asyncio,time
from typing import Dict
import logging.config
from fastapi import APIRouter, WebSocket , WebSocketDisconnect
from common.constant import const
from common.enum import ContentEnum
from . import schemas
from who_is_undercover_backend import WhoIsUndercover,Player

logging.config.fileConfig('logging.conf', disable_existing_loggers=False)
logger = logging.getLogger(const.LOGGER_API)
router = APIRouter(prefix="/game", tags=["game"])

websockets: Dict[str, WebSocket] = {}
game_obj: WhoIsUndercover = None
vote_event = threading.Event()
prefer_words: list[str] = []
second_agent_prefer_words: str = None


@router.get("/china-ware-words", response_model=list[schemas.ChinaWareWord])
def china_ware_words() -> list[schemas.ChinaWareWord]:
    return const.CHINAWARE_WORDS_LIST


@router.post("/begin", response_model=schemas.CommonResponse)
async def begin(game: schemas.Game) -> schemas.CommonResponse:
    logger.info(game)

    global game_obj
    game_obj = WhoIsUndercover(
        is_about_chinaware=game.is_about_chinaware,
        common_word=game.common_word,
        undercover_word=game.undercover_word,
        player_num=6,
        llm_model_id="anthropic.claude-3-sonnet-20240229-v1:0",
    )
    vote_event.clear()
    global prefer_words
    prefer_words = game.prefer_words
    global second_agent_prefer_words
    second_agent_prefer_words = None

    await broadcast(ContentEnum.GAME_BEGIN)
    return schemas.CommonResponse(message="OK")


@router.post("/next-turn")
def next_turn():
    asyncio.run(do_next_trun())

async def do_next_trun():
    await broadcast(ContentEnum.TURN_SPEAK_BEGIN, {"TurnNumber":game_obj.current_turn})

    for player_statement in game_obj.next_turn_statement():
        player:Player = player_statement['player']
        if player.active:
            logger.info(f'Player {player.player_id} 开始陈述。')
        else:
            continue
        await broadcast(ContentEnum.AGENT_SPEAK_BEGIN,{"SpeakAgentId":player.player_id})

        his = player.history[-1]
        logger.info(his['statement'])
        logger.info(f"**Thinking:** {his['thinking']}")
        await unicast(player.player_id, ContentEnum.AGENT_SPEAK_THINKING, f"**Thinking:** {his['thinking']}")
        await unicast(player.player_id, ContentEnum.AGENT_SPEAK, his['statement'])
        await broadcast(ContentEnum.AGENT_SPEAK_END,{"SpeakAgentId":player.player_id})

        # 第1轮设置Agent2的思考方向
        if game_obj.is_about_chinaware and game_obj.current_turn == 1 and player.player_id == "1":
            await unicast("2", ContentEnum.AGENT_SPEAK_CHOOSE, prefer_words)

            logger.info("等待选择")
            vote_event.wait(timeout=20)
            if vote_event.is_set():
                logger.info(f"接收到{second_agent_prefer_words}")
                game_obj.second_agent_prefer_words = second_agent_prefer_words
            else:
                logger.info("超时设置")
                game_obj.second_agent_prefer_words = prefer_words[0]

    await broadcast(ContentEnum.TURN_SPEAK_END, {"TurnNumber":game_obj.current_turn})

    await broadcast(ContentEnum.TURN_VOTE_BEGIN, {"TurnNumber":game_obj.current_turn})
    logger.info(f"第{game_obj.current_turn}轮投票开始")

    for player_vote in game_obj.next_turn_vote():
        player: Player = player_vote['player']
        await broadcast(ContentEnum.AGENT_VOTE_BEGIN,{"SpeakAgentId":player.player_id})
        logger.info(f'Player {player.player_id} 投票给 Player {player_vote["vote"]}')
        logger.info(f"**Thinking:** {player.vote_history[-1]['thinking']}")
        await unicast(player.player_id, ContentEnum.AGENT_VOTE_THINKING, f"**Thinking:** {player.vote_history[-1]['thinking']}")
        await unicast(player.player_id, ContentEnum.AGENT_VOTE, f'投票给 Player {player_vote["vote"]}')
        logger.info(f'Player {player.player_id} 完成投票。')
        await broadcast(ContentEnum.AGENT_VOTE_END,{"SpeakAgentId":player.player_id})
        
    out_player = game_obj.execute_vote_result()
    logger.info(f'Player {out_player.player_id} 被投票出局！')
    await broadcast(ContentEnum.TURN_VOTE_END, {"TurnNumber":game_obj.current_turn,"OutAgentId":out_player.player_id})
    
    game_obj.current_turn += 1
    if game_obj.is_game_close():
        logger.info(f'游戏结束')
        logger.info(game_obj.game_status)
        logger.info(f'平民词: {game_obj.common_word}, 卧底词: {game_obj.undercover_word}')
        await broadcast(ContentEnum.GAME_END, {"Status":game_obj.game_status,
                                               "CommonWord":game_obj.common_word,
                                               "UndercoverWord":game_obj.undercover_word,
                                               })


@router.post("/second-agent-prefer-words", response_model=schemas.CommonResponse)
def second_agent_prefer_words(prefer_words_in: str) -> schemas.CommonResponse:
    logger.info(f"prefer_words:{prefer_words_in}")
    global second_agent_prefer_words
    second_agent_prefer_words = prefer_words_in
    vote_event.set()
    return schemas.CommonResponse(message="OK")


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


async def unicast(agent_id: str, content_type: ContentEnum, content=None):
    websocket = websockets[agent_id]
    content_obj = {
        "agent_id": agent_id,
        "content_type": content_type.value,
        "content": content,
    }
    final_content = json.dumps(content_obj)
    await websocket.send_text(final_content)


async def broadcast(content_type: ContentEnum, content=None):
    for agent_id in websockets:
        await unicast(agent_id, content_type, content)
