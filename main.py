from contextlib import asynccontextmanager
from enum import Enum
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import EmailStr
from sqlmodel import Field, Session, SQLModel, create_engine, select


class EventStatus(str, Enum):
    OPEN = "Open"
    CLOSED = "Closed"


class EventBase(SQLModel):
    title: str = Field(min_length=1, max_length=150)
    venue: str = Field(min_length=1, max_length=150)
    capacity: int = Field(gt=0)
    organizer: str = Field(min_length=1, max_length=100)
    status: EventStatus


class Event(EventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)


class EventUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=150)
    venue: str | None = Field(default=None, min_length=1, max_length=150)
    capacity: int | None = Field(default=None, gt=0)
    organizer: str | None = Field(default=None, min_length=1, max_length=100)
    status: EventStatus | None = None


class ReservationBase(SQLModel):
    student_name: str = Field(min_length=1, max_length=100)
    roll_number: str = Field(min_length=1, max_length=50)
    email: EmailStr


class Reservation(ReservationBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="event.id", index=True)


class Availability(SQLModel):
    capacity: int
    booked: int
    remaining: int


sqlite_file_name = "events.db"
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
    title="Campus Event Seat Reservation API",
    description="FastAPI + SQLModel + SQLite practical assessment Task 2",
    version="1.0.0",
    lifespan=lifespan,
)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_event_or_404(event_id: int, session: Session) -> Event:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def get_booked_count(event_id: int, session: Session) -> int:
    reservations = session.exec(
        select(Reservation).where(Reservation.event_id == event_id)
    ).all()
    return len(reservations)


@app.post("/events", response_model=Event, status_code=201, tags=["Events"])
def create_event(event: EventBase, session: SessionDep):
    db_event = Event.model_validate(event)
    db_event.title = db_event.title.strip()
    db_event.venue = db_event.venue.strip()
    db_event.organizer = db_event.organizer.strip()

    if not db_event.title or not db_event.venue or not db_event.organizer:
        raise HTTPException(status_code=422, detail="Text fields must not be empty")

    session.add(db_event)
    session.commit()
    session.refresh(db_event)
    return db_event


@app.get("/events", response_model=list[Event], tags=["Events"])
def get_events(session: SessionDep):
    return session.exec(select(Event)).all()


@app.get("/events/{event_id}", response_model=Event, tags=["Events"])
def get_event(event_id: int, session: SessionDep):
    return get_event_or_404(event_id, session)


@app.put("/events/{event_id}", response_model=Event, tags=["Events"])
def update_event(event_id: int, event_update: EventUpdate, session: SessionDep):
    event = get_event_or_404(event_id, session)
    updates = event_update.model_dump(exclude_unset=True)

    for field_name, value in updates.items():
        if field_name in {"title", "venue", "organizer"}:
            value = value.strip()
            if not value:
                raise HTTPException(status_code=422, detail=f"{field_name} must not be empty")
        setattr(event, field_name, value)

    booked = get_booked_count(event_id, session)
    if event.capacity < booked:
        raise HTTPException(
            status_code=400,
            detail=f"Capacity cannot be less than current bookings ({booked})",
        )

    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@app.delete("/events/{event_id}", tags=["Events"])
def delete_event(event_id: int, session: SessionDep):
    event = get_event_or_404(event_id, session)

    reservations = session.exec(
        select(Reservation).where(Reservation.event_id == event_id)
    ).all()
    for reservation in reservations:
        session.delete(reservation)

    session.delete(event)
    session.commit()
    return {"message": "Event and its reservations deleted successfully", "id": event_id}


@app.post(
    "/events/{event_id}/reserve",
    response_model=Reservation,
    status_code=201,
    tags=["Reservations"],
)
def reserve_seat(event_id: int, reservation: ReservationBase, session: SessionDep):
    event = get_event_or_404(event_id, session)

    if event.status != "Open":
        raise HTTPException(
            status_code=409,
            detail="Reservations are not allowed because the event is closed",
        )

    booked = get_booked_count(event_id, session)
    if booked >= event.capacity:
        raise HTTPException(status_code=409, detail="Event is full; no seats available")

    db_reservation = Reservation(
        event_id=event_id,
        student_name=reservation.student_name.strip(),
        roll_number=reservation.roll_number.strip(),
        email=reservation.email,
    )

    if not db_reservation.student_name or not db_reservation.roll_number:
        raise HTTPException(status_code=422, detail="Student name and roll number must not be empty")

    session.add(db_reservation)
    session.commit()
    session.refresh(db_reservation)
    return db_reservation


@app.get(
    "/events/{event_id}/reservations",
    response_model=list[Reservation],
    tags=["Reservations"],
)
def get_reservations(event_id: int, session: SessionDep):
    get_event_or_404(event_id, session)
    return session.exec(
        select(Reservation).where(Reservation.event_id == event_id)
    ).all()


@app.delete("/reservations/{reservation_id}", tags=["Reservations"])
def cancel_reservation(reservation_id: int, session: SessionDep):
    reservation = session.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")

    session.delete(reservation)
    session.commit()
    return {"message": "Reservation cancelled successfully", "id": reservation_id}


@app.get(
    "/events/{event_id}/availability",
    response_model=Availability,
    tags=["Reservations"],
)
def get_availability(event_id: int, session: SessionDep):
    event = get_event_or_404(event_id, session)
    booked = get_booked_count(event_id, session)
    return Availability(
        capacity=event.capacity,
        booked=booked,
        remaining=event.capacity - booked,
    )
