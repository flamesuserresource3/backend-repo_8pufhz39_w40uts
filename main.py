import os
from datetime import datetime
from typing import List, Optional

from bson import ObjectId
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db
from schemas import Movie, Theater, Showtime, Booking

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utility converters

def str_id(doc):
    if not doc:
        return doc
    doc["id"] = str(doc.pop("_id"))
    return doc


def get_objectid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")


@app.get("/")
def read_root():
    return {"message": "Movie Booking Backend Ready"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_name"] = getattr(db, "name", "✅ Connected")
            response["connection_status"] = "Connected"
            try:
                response["collections"] = db.list_collection_names()
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


# Movies
@app.post("/movies")
def create_movie(movie: Movie):
    data = movie.model_dump()
    data["created_at"] = datetime.utcnow()
    data["updated_at"] = datetime.utcnow()
    result = db["movie"].insert_one(data)
    return {"id": str(result.inserted_id)}


@app.post("/movies/upload")
async def create_movie_with_upload(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    duration_minutes: Optional[int] = Form(None),
    image: UploadFile = File(None),
):
    poster_data_url = None
    if image is not None:
        content = await image.read()
        mime = image.content_type or "image/png"
        import base64

        b64 = base64.b64encode(content).decode("utf-8")
        poster_data_url = f"data:{mime};base64,{b64}"

    movie = Movie(
        title=title,
        description=description,
        duration_minutes=duration_minutes,
        poster_image=poster_data_url,
    )
    return create_movie(movie)


@app.get("/movies")
def list_movies():
    docs = list(db["movie"].find())
    return [str_id(d) for d in docs]


# Theaters
@app.post("/theaters")
def create_theater(theater: Theater):
    data = theater.model_dump()
    data["created_at"] = datetime.utcnow()
    data["updated_at"] = datetime.utcnow()
    result = db["theater"].insert_one(data)
    return {"id": str(result.inserted_id)}


@app.get("/theaters")
def list_theaters():
    docs = list(db["theater"].find())
    return [str_id(d) for d in docs]


# Showtimes
@app.post("/showtimes")
def create_showtime(showtime: Showtime):
    data = showtime.model_dump()
    # Validate referenced IDs exist
    movie_exists = db["movie"].count_documents({"_id": get_objectid(data["movie_id"])}, limit=1)
    theater_exists = db["theater"].count_documents({"_id": get_objectid(data["theater_id"])}, limit=1)
    if not movie_exists or not theater_exists:
        raise HTTPException(status_code=400, detail="Invalid movie_id or theater_id")

    if data.get("seats_available") is None:
        data["seats_available"] = data["total_seats"]

    # Convert references to ObjectId
    data["movie_id"] = get_objectid(data["movie_id"])
    data["theater_id"] = get_objectid(data["theater_id"])
    data["created_at"] = datetime.utcnow()
    data["updated_at"] = datetime.utcnow()

    result = db["showtime"].insert_one(data)
    return {"id": str(result.inserted_id)}


class ShowtimeOut(BaseModel):
    id: str
    movie_id: str
    theater_id: str
    start_time: datetime
    total_seats: int
    seats_available: int
    movie_title: Optional[str] = None
    theater_name: Optional[str] = None
    theater_location: Optional[str] = None


@app.get("/showtimes", response_model=List[ShowtimeOut])
def list_showtimes():
    docs = list(db["showtime"].find())
    out = []
    for d in docs:
        sd = str_id(d)
        # Expand references
        m = db["movie"].find_one({"_id": sd and ObjectId(sd.get("movie_id"))}) if False else None
        # Since movie_id/theater_id were stored as ObjectId, recover them
        movie_oid = d.get("movie_id")
        theater_oid = d.get("theater_id")
        movie = db["movie"].find_one({"_id": movie_oid}) if movie_oid else None
        theater = db["theater"].find_one({"_id": theater_oid}) if theater_oid else None
        out.append(
            ShowtimeOut(
                id=sd["id"],
                movie_id=str(movie_oid) if movie_oid else "",
                theater_id=str(theater_oid) if theater_oid else "",
                start_time=d.get("start_time"),
                total_seats=d.get("total_seats", 0),
                seats_available=d.get("seats_available", 0),
                movie_title=(movie or {}).get("title"),
                theater_name=(theater or {}).get("name"),
                theater_location=(theater or {}).get("location"),
            )
        )
    return out


# Booking
@app.post("/bookings")
def create_booking(booking: Booking):
    data = booking.model_dump()
    showtime_oid = get_objectid(data["showtime_id"])

    st = db["showtime"].find_one({"_id": showtime_oid})
    if not st:
        raise HTTPException(status_code=404, detail="Showtime not found")

    seats = int(data["seats"]) if isinstance(data["seats"], str) else data["seats"]
    available = int(st.get("seats_available", 0))
    if seats <= 0:
        raise HTTPException(status_code=400, detail="Seats must be greater than 0")
    if seats > available:
        raise HTTPException(status_code=400, detail="Not enough seats available")

    # Create booking
    booking_doc = {
        "showtime_id": showtime_oid,
        "customer_name": data["customer_name"],
        "seats": seats,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    result = db["booking"].insert_one(booking_doc)

    # Decrement seats
    db["showtime"].update_one(
        {"_id": showtime_oid}, {"$inc": {"seats_available": -seats}, "$set": {"updated_at": datetime.utcnow()}}
    )

    return {"id": str(result.inserted_id)}


@app.get("/bookings")
def list_bookings():
    docs = list(db["booking"].find())
    out = []
    for d in docs:
        sd = str_id(d)
        st = db["showtime"].find_one({"_id": d.get("showtime_id")})
        movie = None
        theater = None
        if st:
            movie = db["movie"].find_one({"_id": st.get("movie_id")})
            theater = db["theater"].find_one({"_id": st.get("theater_id")})
        sd["movie_title"] = (movie or {}).get("title")
        sd["theater_name"] = (theater or {}).get("name")
        out.append(sd)
    return out


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
