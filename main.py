from contextlib import asynccontextmanager
from contextlib import asynccontextmanager
from enum import Enum
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlmodel import Field, Session, SQLModel, create_engine, select

class Status(str, Enum):
    LOST = "Lost"
    FOUND = "Found"
    RETURNED = "Returned"


class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=10, max_length=500)
    category: str = Field(min_length=1, max_length=50)
    location: str = Field(min_length=1, max_length=150)
    reported_by: str = Field(min_length=1, max_length=100)
    status: Status

    @classmethod
    def model_validate_clean(cls, value):
        # Kept for compatibility with plain SQLModel usage; normal FastAPI
        # validation happens through the Pydantic/SQLModel fields above.
        return cls.model_validate(value)


class Item(ItemBase, table=True):
    id: int | None = Field(default=None, primary_key=True)


class ItemUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=10, max_length=500)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    location: str | None = Field(default=None, min_length=1, max_length=150)
    reported_by: str | None = Field(default=None, min_length=1, max_length=100)
    status: Status | None = None


sqlite_file_name = "lost_found.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(
    sqlite_url,
    connect_args={"check_same_thread": False},
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(
    title="Campus Lost & Found API",
    description="FastAPI + SQLModel + SQLite practical assessment Task 1",
    version="1.0.0",
    lifespan=lifespan,
)


def get_session():
    with Session(engine) as session:
        yield session


@app.post("/items", response_model=Item, status_code=201, tags=["Items"])
def create_item(item: ItemBase, session: Session = Depends(get_session)):
    clean_item = item.model_copy(
        update={
            "title": item.title.strip(),
            "description": item.description.strip(),
            "category": item.category.strip(),
            "location": item.location.strip(),
            "reported_by": item.reported_by.strip(),
        }
    )
    for field_name in ("title", "description", "category", "location", "reported_by"):
        if not getattr(clean_item, field_name):
            raise HTTPException(status_code=422, detail=f"{field_name} must not be empty")

    db_item = Item.model_validate(clean_item)
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


@app.get("/items", response_model=list[Item], tags=["Items"])
def get_items(session: Session = Depends(get_session)):
    return session.exec(select(Item)).all()


@app.get("/items/status/{status}", response_model=list[Item], tags=["Filters"])
def get_items_by_status(status: Status, session: Session = Depends(get_session)):
    return session.exec(select(Item).where(Item.status == status)).all()


@app.get("/items/category/{category}", response_model=list[Item], tags=["Filters"])
def get_items_by_category(category: str, session: Session = Depends(get_session)):
    return session.exec(select(Item).where(Item.category == category)).all()


@app.get("/items/{item_id}", response_model=Item, tags=["Items"])
def get_item(item_id: int, session: Session = Depends(get_session)):
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.put("/items/{item_id}", response_model=Item, tags=["Items"])
def update_item(
    item_id: int,
    item_update: ItemUpdate,
    session: Session = Depends(get_session),
):
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    updates = item_update.model_dump(exclude_unset=True)
    string_fields = {"title", "description", "category", "location", "reported_by"}

    for field_name, value in updates.items():
        if field_name in string_fields:
            value = value.strip()
            if not value:
                raise HTTPException(status_code=422, detail=f"{field_name} must not be empty")
        setattr(item, field_name, value)

    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@app.delete("/items/{item_id}", tags=["Items"])
def delete_item(item_id: int, session: Session = Depends(get_session)):
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    session.delete(item)
    session.commit()
    return {"message": "Item deleted successfully", "id": item_id}
