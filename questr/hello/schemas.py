from pydantic import BaseModel


class HelloResponse(BaseModel):
    message: str

    model_config = {'from_attributes': True}
