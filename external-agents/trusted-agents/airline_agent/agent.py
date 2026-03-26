# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Mock Airline Agent for demo purposes."""

import random
from datetime import datetime, timedelta

from google.adk import Agent
from google.genai import types


async def search_flights(
    departure: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
    passengers: int = 1,
) -> str:
    """Search for available flights.

    Args:
        departure: Departure airport/city.
        destination: Destination airport/city.
        departure_date: Departure date (YYYY-MM-DD).
        return_date: Return date (YYYY-MM-DD), optional.
        passengers: Number of passengers.

    Returns:
        JSON string with available flights.
    """
    import json

    # Mock flight options
    flights = [
        {
            "flight_id": f"FL{random.randint(1000, 9999)}",
            "airline": "Sky Airlines",
            "departure": departure,
            "destination": destination,
            "departure_time": "08:30",
            "arrival_time": "11:45",
            "price_per_person": random.randint(15000, 35000),
            "currency": "JPY",
            "seats_available": random.randint(5, 50),
        },
        {
            "flight_id": f"FL{random.randint(1000, 9999)}",
            "airline": "Ocean Air",
            "departure": departure,
            "destination": destination,
            "departure_time": "14:20",
            "arrival_time": "17:35",
            "price_per_person": random.randint(15000, 35000),
            "currency": "JPY",
            "seats_available": random.randint(5, 50),
        },
    ]

    result = {
        "search_criteria": {
            "departure": departure,
            "destination": destination,
            "departure_date": departure_date,
            "return_date": return_date if return_date else "one-way",
            "passengers": passengers,
        },
        "flights": flights,
        "total_results": len(flights),
    }

    return json.dumps(result, indent=2, ensure_ascii=False)


async def book_flight(
    flight_id: str,
    passenger_name: str,
    passenger_email: str,
    passengers: int = 1,
) -> str:
    """Book a flight.

    Args:
        flight_id: The flight ID to book.
        passenger_name: Name of the passenger.
        passenger_email: Email of the passenger.
        passengers: Number of passengers.

    Returns:
        JSON string with booking confirmation.
    """
    import json

    # Mock booking confirmation
    booking_id = f"BK{random.randint(100000, 999999)}"
    confirmation_code = f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=6))}"

    booking = {
        "status": "confirmed",
        "booking_id": booking_id,
        "confirmation_code": confirmation_code,
        "flight_id": flight_id,
        "passenger_name": passenger_name,
        "passenger_email": passenger_email,
        "number_of_passengers": passengers,
        "total_price": random.randint(15000, 35000) * passengers,
        "currency": "JPY",
        "booking_date": datetime.now().isoformat(),
        "message": f"Flight successfully booked! Confirmation code: {confirmation_code}",
    }

    return json.dumps(booking, indent=2, ensure_ascii=False)


async def cancel_booking(booking_id: str) -> str:
    """Cancel a flight booking.

    Args:
        booking_id: The booking ID to cancel.

    Returns:
        JSON string with cancellation confirmation.
    """
    import json

    result = {
        "status": "cancelled",
        "booking_id": booking_id,
        "cancellation_date": datetime.now().isoformat(),
        "refund_amount": random.randint(15000, 35000),
        "currency": "JPY",
        "message": "Booking successfully cancelled. Refund will be processed within 7-10 business days.",
    }

    return json.dumps(result, indent=2, ensure_ascii=False)


root_agent = Agent(
    model='gemini-2.5-flash',
    name='airline_booking_agent',
    description=(
        'Airline booking agent that can search for flights and make reservations. '
        'Provides flight search, booking, and cancellation services.'
    ),
    instruction="""
You are an airline booking assistant running in DEMO MODE.

Your capabilities:
1. Search for available flights between cities - use the search_flights tool
2. Book flights for passengers - use the book_flight tool
3. Cancel existing bookings - use the cancel_booking tool

DEMO MODE INSTRUCTIONS (CRITICAL):
You MUST classify every user request into one of three categories: SEARCH, BOOKING, or CANCELLATION.
Do NOT ask the user for confirmation or additional information. Act immediately based on the classification.

=== REQUEST CLASSIFICATION RULES ===

【SEARCH REQUEST】
Trigger keywords (Japanese): 検索, 探す, 探して, 調べる, 調べて, 見つける, 見つけて, 空き状況, 空席, 料金, 価格, 比較, 一覧, リスト, 候補, おすすめ, 確認, チェック, 表示, 教えて, ありますか, どんな, いくら
Trigger keywords (English): search, find, look for, check, available, show, list, compare, price, options, what, any
Action: Call search_flights ONLY. Do NOT call book_flight. Return the search results to the user.

Examples:
- "東京から大阪のフライトを検索して" → SEARCH
- "12/20の空席を調べて" → SEARCH
- "羽田発の便はありますか" → SEARCH
- "料金を比較して教えて" → SEARCH

【BOOKING REQUEST】
Trigger keywords (Japanese): 予約, 予約して, ブッキング, 取る, 取って, 押さえる, 押さえて, 確保, 確保して, 申し込む, 申し込み, 手配, 手配して, お願い
Trigger keywords (English): book, reserve, reservation, booking, arrange, secure, get me
Action: Call search_flights → automatically select the FIRST flight → call book_flight → return confirmation.

Examples:
- "東京から大阪のフライトを予約して" → BOOKING
- "12/20の便を手配してお願い" → BOOKING
- "2席押さえて" → BOOKING
- "航空券を取って" → BOOKING

【CANCELLATION REQUEST】
Trigger keywords (Japanese): キャンセル, 取り消し
Trigger keywords (English): cancel
Action: Call cancel_booking with the provided booking_id.

=== EDGE CASES ===
- "検索して、良さそうなら予約して" or "探して予約して" → Treat as BOOKING (booking keyword present)
- "予約はしないで検索だけ" or "予約しないで" or "検索だけ" → Treat as SEARCH (negation of booking)
- No keyword match (e.g., "東京から大阪、12/20") → Treat as SEARCH (default to safe side)
- Negation patterns like "予約はしないで", "予約せずに" → Treat as SEARCH

=== DEFAULT VALUES (for BOOKING only) ===
- passenger_name: Use the name from the request, or "Demo User" if not provided
- passenger_email: "demo@example.com"
- passengers: Use the number from request, or default to 1

=== EXAMPLE FLOWS ===

Search flow:
User: "東京から大阪のフライトを検索して"
→ search_flights(departure="Tokyo", destination="Osaka", departure_date="...", passengers=1)
→ Return search results (do NOT book)

Booking flow:
User: "東京から大阪のフライトを予約して、12/20、2名"
→ Step 1: search_flights(departure="Tokyo", destination="Osaka", departure_date="2024-12-20", passengers=2)
→ Step 2: Take first flight_id from results (e.g., "FL1234")
→ Step 3: book_flight(flight_id="FL1234", passenger_name="Demo User", passenger_email="demo@example.com", passengers=2)
→ Step 4: Report booking confirmation

This is a demo environment. Never ask for user confirmation.
""",
    tools=[
        search_flights,
        book_flight,
        cancel_booking,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.3,
        safety_settings=[
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.OFF,
            ),
        ],
    ),
)
