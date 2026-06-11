from datetime import date, datetime
from typing import Any

from fastapi.encoders import jsonable_encoder


def serialize_sqlalchemy(model: Any) -> Any:
    if model is None:
        return None

    if not hasattr(model, "__table__"):
        return jsonable_encoder(model)

    data = {}
    for column in model.__table__.columns:
        data[column.name] = getattr(model, column.name)

    return jsonable_encoder(data)


def serialize_sqlalchemy_list(models: list[Any]) -> list[Any]:
    return [serialize_sqlalchemy(item) for item in models]


def serialize_response(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            key: serialize_response(item)
            for key, item in value.items()
            if key != "_sa_instance_state"
        }

    if isinstance(value, (list, tuple, set)):
        return [serialize_response(item) for item in value]

    if hasattr(value, "__table__"):
        return serialize_sqlalchemy(value)

    return jsonable_encoder(value)
