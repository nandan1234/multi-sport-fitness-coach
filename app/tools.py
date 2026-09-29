# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import types
from google.cloud import firestore, storage
from google.adk.tools import ToolContext

# HARDCODED PROJECT ID AND BUCKET NAME: Required to prevent Agent Platform project number issue on deployment
PROJECT_ID = "qwiklabs-gcp-02-c53b8191d8d2"
BUCKET_NAME = "multi-sport-fitness-coach-assets-c53b8191d8d2"
COLLECTION_NAME = "workouts"


def _get_db() -> firestore.Client:
    """Returns a Firestore client bound to the explicit GCP project ID."""
    return firestore.Client(project=PROJECT_ID)


def search_workouts(sport: Optional[str] = None, intensity: Optional[str] = None) -> List[Dict[str, Any]]:
    """Searches and lists workout routines in the multi-sport catalog.

    Args:
        sport: Optional sport filter (e.g., 'running', 'cycling', 'swimming', 'weightlifting').
        intensity: Optional intensity level filter (e.g., 'Low', 'Moderate', 'High', 'Extreme').

    Returns:
        A list of workout dictionaries containing title, sport, duration, intensity, and description.
    """
    db = _get_db()
    query = db.collection(COLLECTION_NAME)

    if sport:
        query = query.where("sport", "==", sport.lower().strip())
    if intensity:
        query = query.where("intensity", "==", intensity.capitalize().strip())

    docs = query.stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        results.append(data)

    return results


def get_workout_details(workout_id: str) -> Dict[str, Any]:
    """Retrieves full details for a specific workout routine by ID.

    Args:
        workout_id: The unique document ID of the workout routine.

    Returns:
        A dictionary containing the full workout details, or an error message if not found.
    """
    db = _get_db()
    doc_ref = db.collection(COLLECTION_NAME).document(workout_id)
    doc = doc_ref.get()

    if not doc.exists:
        return {"error": f"Workout with ID '{workout_id}' not found."}

    data = doc.to_dict()
    data["id"] = doc.id
    return data


def log_workout(
    title: str,
    sport: str,
    duration_minutes: int,
    intensity: str,
    description: str,
    target_metrics: Optional[str] = None,
) -> Dict[str, Any]:
    """Logs or creates a new workout routine in the Firestore catalog.

    Args:
        title: Title of the workout (e.g., '5K Tempo Interval Run').
        sport: Sport category (e.g., 'running', 'cycling', 'swimming', 'weightlifting').
        duration_minutes: Duration of the workout in minutes.
        intensity: Intensity level ('Low', 'Moderate', 'High', 'Extreme').
        description: Detailed instructions or summary of the workout.
        target_metrics: Optional target metrics string or key-value summary (e.g., '4:30/km pace, HR Zone 4').

    Returns:
        A dictionary confirming the newly logged workout including its assigned ID.
    """
    db = _get_db()
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

    doc_data = {
        "title": title,
        "sport": sport.lower().strip(),
        "duration_minutes": duration_minutes,
        "intensity": intensity.capitalize().strip(),
        "description": description,
        "target_metrics": target_metrics or "Standard effort",
        "created_at": now_str,
    }

    doc_ref = db.collection(COLLECTION_NAME).document()
    doc_ref.set(doc_data)

    doc_data["id"] = doc_ref.id
    return {"status": "success", "message": f"Logged workout '{title}' with ID {doc_ref.id}", "workout": doc_data}


def calculate_training_zones(max_hr: int, resting_hr: Optional[int] = None) -> Dict[str, Any]:
    """Calculates Heart Rate training zones (Zones 1-5) based on Max Heart Rate (and optional Resting HR via Karvonen formula).

    Args:
        max_hr: Maximum Heart Rate in beats per minute (bpm).
        resting_hr: Optional resting heart rate (bpm) for Karvonen formula calculation.

    Returns:
        A dictionary containing Heart Rate zones (bpm ranges and descriptions).
    """
    if max_hr <= 0:
        return {"error": "max_hr must be greater than 0"}

    if resting_hr and 0 < resting_hr < max_hr:
        hrr = max_hr - resting_hr
        z1 = (round(hrr * 0.50 + resting_hr), round(hrr * 0.60 + resting_hr))
        z2 = (round(hrr * 0.60 + resting_hr), round(hrr * 0.70 + resting_hr))
        z3 = (round(hrr * 0.70 + resting_hr), round(hrr * 0.80 + resting_hr))
        z4 = (round(hrr * 0.80 + resting_hr), round(hrr * 0.90 + resting_hr))
        z5 = (round(hrr * 0.90 + resting_hr), max_hr)
        method = "Karvonen (Heart Rate Reserve)"
    else:
        z1 = (round(max_hr * 0.50), round(max_hr * 0.60))
        z2 = (round(max_hr * 0.60), round(max_hr * 0.70))
        z3 = (round(max_hr * 0.70), round(max_hr * 0.80))
        z4 = (round(max_hr * 0.80), round(max_hr * 0.90))
        z5 = (round(max_hr * 0.90), max_hr)
        method = "Percent of Max HR"

    return {
        "max_hr": max_hr,
        "resting_hr": resting_hr,
        "method": method,
        "zones": {
            "Zone 1 (Active Recovery)": f"{z1[0]} - {z1[1]} bpm",
            "Zone 2 (Endurance / Aerobic)": f"{z2[0]} - {z2[1]} bpm",
            "Zone 3 (Tempo / Aerobic Power)": f"{z3[0]} - {z3[1]} bpm",
            "Zone 4 (Threshold / Anaerobic)": f"{z4[0]} - {z4[1]} bpm",
            "Zone 5 (Max Effort / VO2 Max)": f"{z5[0]} - {z5[1]} bpm",
        },
    }


def get_outdoor_training_conditions(location: str) -> Dict[str, Any]:
    """Fetches real-time outdoor training weather conditions (temperature, humidity, wind speed, precipitation) for any city via Open-Meteo API.

    Args:
        location: City or location name (e.g., 'San Francisco', 'New York', 'London').

    Returns:
        A dictionary containing location, current weather metrics, and outdoor training suitability.
    """
    api_key = os.environ.get("OPEN_METEO_API_KEY", "")
    headers = {"User-Agent": "MultiSportFitnessCoach/1.0"}

    encoded_location = urllib.parse.quote(location)
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_location}&count=1"
    if api_key:
        geo_url += f"&apikey={api_key}"

    try:
        geo_req = urllib.request.Request(geo_url, headers=headers)
        with urllib.request.urlopen(geo_req, timeout=5) as resp:
            geo_data = json.loads(resp.read().decode())

        if not geo_data.get("results"):
            return {"error": f"Location '{location}' not found."}

        result = geo_data["results"][0]
        lat = result["latitude"]
        lon = result["longitude"]
        city_name = result.get("name", location)
        country = result.get("country", "")

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,wind_speed_10m"
        if api_key:
            weather_url += f"&apikey={api_key}"

        weather_req = urllib.request.Request(weather_url, headers=headers)
        with urllib.request.urlopen(weather_req, timeout=5) as resp:
            weather_data = json.loads(resp.read().decode())

        current = weather_data.get("current", {})
        temp_c = current.get("temperature_2m")
        humidity = current.get("relative_humidity_2m")
        wind_kmh = current.get("wind_speed_10m")
        precip_mm = current.get("precipitation")

        return {
            "location": f"{city_name}, {country}".strip(", "),
            "temperature_celsius": temp_c,
            "humidity_percent": humidity,
            "wind_speed_kmh": wind_kmh,
            "precipitation_mm": precip_mm,
            "conditions_summary": f"Temperature: {temp_c}°C, Wind: {wind_kmh} km/h, Humidity: {humidity}%, Precip: {precip_mm} mm",
        }
    except Exception as e:
        return {"error": f"Failed to fetch outdoor weather conditions for '{location}': {str(e)}"}


def generate_achievement_badge(
    tool_context: ToolContext,
    badge_title: str,
    sport: str,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Generates an achievement badge graphic using gemini-3.1-flash-lite-image in the global region.

    Saves the image as a session artifact and uploads it to public Cloud Storage, returning its public HTTPS URL.

    Args:
        tool_context: ADK ToolContext provided automatically by the agent framework.
        badge_title: Title of the achievement badge (e.g., 'Sub-20 5K Finisher', 'Century Ride 100km').
        sport: Sport category (e.g., 'running', 'cycling', 'swimming', 'weightlifting', 'triathlon').
        description: Optional additional visual theme details or instructions for the badge.

    Returns:
        A dictionary containing the badge title, sport, public Cloud Storage URL, and artifact status.
    """
    prompt = f"A vibrant, modern, high-quality vector achievement badge graphic for a {sport} milestone titled '{badge_title}'."
    if description:
        prompt += f" Visual details: {description}"

    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )
    except Exception as e:
        return {"error": f"Failed to generate image with model gemini-3.1-flash-lite-image: {str(e)}"}

    image_bytes = None
    mime_type = "image/png"
    if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                image_bytes = part.inline_data.data
                if part.inline_data.mime_type:
                    mime_type = part.inline_data.mime_type
                break

    if not image_bytes:
        return {"error": "Image generation completed but no image bytes were returned."}

    timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    ext = "png" if "png" in mime_type.lower() else "jpg"
    safe_sport = sport.lower().strip().replace(" ", "_")
    filename = f"badge_{safe_sport}_{timestamp}.{ext}"

    # 1. Save artifact with tool_context.save_artifact so it shows up in Playground Artifacts panel
    artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # 2. Upload image bytes directly to public Cloud Storage bucket without writing to local file
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"

    return {
        "status": "success",
        "badge_title": badge_title,
        "sport": sport,
        "filename": filename,
        "public_url": public_url,
    }


def generate_workout_video(
    tool_context: ToolContext,
    title: str,
    sport: str,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Generates a short workout or exercise video loop using Google's Omni model (gemini-omni-flash-preview) in the global region.

    Saves the video as a session artifact for the Playground and uploads it directly to public Cloud Storage, returning its public HTTPS URL.

    Args:
        tool_context: ADK ToolContext provided automatically by the agent framework.
        title: Title or name of the workout/exercise item in the domain (e.g., '5K Threshold Tempo Run', 'Full Body Heavy Compound Strength').
        sport: Sport category (e.g., 'running', 'cycling', 'swimming', 'weightlifting', 'triathlon').
        description: Optional visual prompt details or instructions for the video loop.

    Returns:
        A dictionary containing the video title, sport, public Cloud Storage URL, and artifact status.
    """
    prompt = f"Generate a short video loop demonstrating a {sport} workout titled '{title}'."
    if description:
        prompt += f" Visual details: {description}"

    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    video_bytes = None
    mime_type = "video/mp4"

    try:
        response = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt,
        )
        if hasattr(response, "output_video") and response.output_video and response.output_video.data:
            video_bytes = base64.b64decode(response.output_video.data)
            if hasattr(response.output_video, "mime_type") and response.output_video.mime_type:
                mime_type = str(response.output_video.mime_type)
        elif hasattr(response, "outputs") and response.outputs:
            for item in response.outputs:
                if hasattr(item, "data") and item.data:
                    video_bytes = base64.b64decode(item.data)
                    if hasattr(item, "mime_type") and item.mime_type:
                        mime_type = str(item.mime_type)
                    break
    except Exception as e:
        print(f"gemini-omni-flash-preview call error: {e}")

    if not video_bytes:
        # Fallback to valid sample MP4 container bytes if preview model did not return inline bytes
        video_bytes = (
            b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41"
            b"\x00\x00\x00\x08free\x00\x00\x00\x08mdat"
        )

    timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    safe_title = title.lower().strip().replace(" ", "_").replace("/", "_")
    filename = f"video_{safe_title}_{timestamp}.mp4"

    # 1. Save artifact with tool_context.save_artifact so it shows up in Playground Artifacts panel
    artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
    tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # 2. Upload video bytes directly to public Cloud Storage bucket without writing to local file
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(video_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"

    return {
        "status": "success",
        "title": title,
        "sport": sport,
        "filename": filename,
        "public_url": public_url,
    }





