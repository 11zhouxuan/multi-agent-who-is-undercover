from typing import Optional,Union
from pydantic import BaseModel, Field

class Game(BaseModel):
    is_about_chinaware: bool
    common_word: str
    undercover_word: str
    prefer_words: list[str]


class CommonResponse(BaseModel):
    message: str


class ChinaWareWord(BaseModel):
    undercover_word: str
    common_word: str
    prefer_words: list[str]