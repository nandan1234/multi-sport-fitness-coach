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

import datetime
from google.cloud import firestore

# HARDCODED PROJECT ID: Required to prevent Agent Platform project number issue on deployment
PROJECT_ID = "qwiklabs-gcp-02-c53b8191d8d2"
COLLECTION_NAME = "workouts"

SEED_WORKOUTS = [
    {
        "id": "workout-001",
        "title": "5K Threshold Tempo Run",
        "sport": "running",
        "duration_minutes": 35,
        "intensity": "High",
        "description": "10 min warm-up, 20 min threshold pace at lactate threshold (Zone 4), 5 min cool-down.",
        "target_metrics": "Target Pace: 4:25/km, HR Zone 4 (80-90% Max HR)",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    },
    {
        "id": "workout-002",
        "title": "100km Gran Fondo Endurance Ride",
        "sport": "cycling",
        "duration_minutes": 180,
        "intensity": "Moderate",
        "description": "Steady aerobic zone endurance ride with cadence drills (85-95 RPM) and fueling every 30 mins.",
        "target_metrics": "Target Power: 180W-210W (Zone 2), Cadence 90 RPM",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    },
    {
        "id": "workout-003",
        "title": "Full Body Heavy Compound Strength",
        "sport": "weightlifting",
        "duration_minutes": 50,
        "intensity": "High",
        "description": "Barbell Squats 4x5, Bench Press 4x5, Deadlifts 3x5, and Weighted Pull-ups 3x8.",
        "target_metrics": "Rest: 2-3 mins between heavy sets, RPE 8-9",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    },
    {
        "id": "workout-004",
        "title": "1500m Open Water Swim Pyramid",
        "sport": "swimming",
        "duration_minutes": 45,
        "intensity": "Moderate",
        "description": "Pyramid intervals: 100m, 200m, 300m, 400m, 300m, 200m, 100m freestyle with 20s rest.",
        "target_metrics": "Target SWOLF: < 35, Pace 1:40/100m",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    },
    {
        "id": "workout-005",
        "title": "Triathlon Brick Workout: Bike + Run",
        "sport": "triathlon",
        "duration_minutes": 75,
        "intensity": "Extreme",
        "description": "45 min high-tempo indoor ride immediately followed by a fast 20 min transition run.",
        "target_metrics": "Transition Time < 90 seconds, Target Run Pace 4:40/km",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    },
]


def seed_firestore():
    print(f"Connecting to Firestore for project: {PROJECT_ID}...")
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection(COLLECTION_NAME)

    for item in SEED_WORKOUTS:
        doc_id = item["id"]
        doc_data = {k: v for k, v in item.items() if k != "id"}
        collection_ref.document(doc_id).set(doc_data)
        print(f"  ✓ Seeded document: {COLLECTION_NAME}/{doc_id} ('{item['title']}')")

    print("Successfully seeded Firestore collection!")


if __name__ == "__main__":
    seed_firestore()
