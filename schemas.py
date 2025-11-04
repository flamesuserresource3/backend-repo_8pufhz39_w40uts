"""
Database Schemas for Movie Booking System

Each Pydantic model corresponds to a MongoDB collection (lowercased class name).
- Movie -> "movie"
- Theater -> "theater"
- Showtime -> "showtime"
- Booking -> "booking"
"""
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional

class Movie(BaseModel):
    title: str = Field(..., description="Movie title")
    description: Optional[str] = Field(None, description="Movie synopsis/description")
    duration_minutes: Optional[int] = Field(None, ge=1, description="Duration in minutes")
    poster_image: Optional[str] = Field(
        None,
        description="Poster image as data URL (e.g., 'data:image/png;base64,...')"
    )

class Theater(BaseModel):
    name: str = Field(..., description="Theater name")
    location: str = Field(..., description="City or address")

class Showtime(BaseModel):
    movie_id: str = Field(..., description="Referenced Movie _id as string")
    theater_id: str = Field(..., description="Referenced Theater _id as string")
    start_time: datetime = Field(..., description="ISO datetime for the show start time")
    total_seats: int = Field(..., ge=1, description="Total seats for the show")
    seats_available: Optional[int] = Field(None, ge=0, description="Available seats; defaults to total_seats")

class Booking(BaseModel):
    showtime_id: str = Field(..., description="Referenced Showtime _id as string")
    customer_name: str = Field(..., description="Name for the booking")
    seats: int = Field(..., ge=1, description="Number of seats to book")
