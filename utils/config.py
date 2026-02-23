from pydantic import BaseModel

class Config(BaseModel):
    save_path: str
    thread_id: str
    question: str
