# Anga Air JSON API v1

A read-only API over flights, fares and live status. Base path: `/api/v1`.

- **Authentication:** none, because everything here is public data.
- **Format:** JSON, with money as integer Kenyan shillings (`KES`).
- **Rate limit:** per IP, using an in-memory token bucket (120 requests a minute, bursts of 40).
  Past that you get `429` with a `Retry-After` header.
- **CORS:** off. No `Access-Control-Allow-Origin` header is sent, so browsers on other origins
  cannot read responses.

## Response envelope

Success:

```json
{ "ok": true, "data": [], "meta": {} }
```

Failure. `fields` appears when the problem is with specific parameters:

```json
{
  "ok": false,
  "error": {
    "code": 400,
    "message": "Some parameters are invalid.",
    "fields": { "date": "Use the format YYYY-MM-DD." }
  }
}
```

| Status | Meaning |
| --- | --- |
| `200` | Success |
| `400` | Invalid parameters; see `error.fields` |
| `404` | Unknown airport, flight or route |
| `405` | The API is read-only: only `GET` is accepted |
| `429` | Rate limit exceeded |

## Endpoints

### `GET /airports`

Every airport in the network.

```bash
curl http://127.0.0.1:5000/api/v1/airports
```

```json
{
  "ok": true,
  "data": [
    {
      "code": "NBO",
      "city": "Nairobi",
      "name": "Jomo Kenyatta International",
      "country": "Kenya",
      "timezone": "Africa/Nairobi",
      "lat": -1.3192,
      "lng": 36.9278
    }
  ],
  "meta": { "count": 12 }
}
```

### `GET /flights`

Flights on a route and date, with live fares.

| Parameter | Required | Notes |
| --- | --- | --- |
| `from` | yes | Origin airport code |
| `to` | yes | Destination airport code; must differ from `from` |
| `date` | yes | `YYYY-MM-DD`, today or later |
| `cabin` | no | `Economy` (default), `Business` or `First` |

```bash
curl "http://127.0.0.1:5000/api/v1/flights?from=NBO&to=MBA&date=2030-01-15&cabin=Economy"
```

```json
{
  "ok": true,
  "data": [
    {
      "flight_number": "AN101",
      "date": "2030-01-15",
      "origin": "NBO",
      "destination": "MBA",
      "departure_time": "08:00",
      "arrival_time": "09:15",
      "duration_minutes": 75,
      "aircraft": "Boeing 737-800",
      "status": "Scheduled",
      "fares": [
        {
          "cabin": "Economy",
          "fare_family": "Lite",
          "price": 8500,
          "currency": "KES",
          "seats_left": 42,
          "bags": 0,
          "changeable": false,
          "refund_rate": 0.0
        }
      ]
    }
  ],
  "meta": {
    "count": 2,
    "origin": "NBO",
    "destination": "MBA",
    "date": "2030-01-15",
    "cabin": "Economy"
  }
}
```

`price` is what a customer would be quoted right now, including weekend and demand pricing, so
it can change between calls.

### `GET /flights/<number>/status`

The live status of one flight. `date` is optional and defaults to today.

```bash
curl "http://127.0.0.1:5000/api/v1/flights/AN101/status?date=2030-01-15"
```

```json
{
  "ok": true,
  "data": {
    "flight_number": "AN101",
    "date": "2030-01-15",
    "origin": "NBO",
    "origin_city": "Nairobi",
    "destination": "MBA",
    "destination_city": "Mombasa",
    "scheduled_departure": "08:00",
    "scheduled_arrival": "09:15",
    "estimated_departure": "08:40",
    "estimated_arrival": "09:55",
    "status": "Delayed",
    "delay_minutes": 40,
    "gate": "B4",
    "progress": 0
  },
  "meta": {}
}
```

`status` is one of `Scheduled`, `On time`, `Delayed`, `Boarding`, `Departed`, `Landed` or
`Cancelled`. `progress` is how far along the route the flight is, from 0 to 100.

### `GET /fare-calendar`

The cheapest fare for each day of a month. Days with no bookable fare are left out.

| Parameter | Required | Notes |
| --- | --- | --- |
| `from` | yes | Origin airport code |
| `to` | yes | Destination airport code |
| `month` | no | `YYYY-MM`; defaults to the current month |
| `cabin` | no | `Economy` (default), `Business` or `First` |

```bash
curl "http://127.0.0.1:5000/api/v1/fare-calendar?from=NBO&to=ZNZ&month=2030-01"
```

```json
{
  "ok": true,
  "data": [{ "date": "2030-01-15", "price": 17500, "currency": "KES", "heat": 0 }],
  "meta": {
    "month": "2030-01",
    "origin": "NBO",
    "destination": "ZNZ",
    "cabin": "Economy",
    "cheapest": 17500,
    "dearest": 21700
  }
}
```

`heat` runs from 0 (the month's cheapest) to 5 (the month's dearest).

### `GET /board/<airport>`

The departures or arrivals board. Flights that landed more than two hours ago drop off, and the
next day's flights follow today's. Each row has the same shape as the status endpoint.

| Parameter | Required | Notes |
| --- | --- | --- |
| `type` | no | `departures` (default) or `arrivals` |

```bash
curl "http://127.0.0.1:5000/api/v1/board/NBO?type=arrivals"
```

```json
{
  "ok": true,
  "data": [
    {
      "flight_number": "AN102",
      "date": "2030-01-15",
      "origin": "MBA",
      "origin_city": "Mombasa",
      "destination": "NBO",
      "destination_city": "Nairobi",
      "scheduled_departure": "10:00",
      "scheduled_arrival": "11:15",
      "estimated_departure": "10:00",
      "estimated_arrival": "11:15",
      "status": "On time",
      "delay_minutes": 0,
      "gate": "A7",
      "progress": 0
    }
  ],
  "meta": { "count": 12, "airport": "NBO", "type": "arrivals", "date": "2030-01-15" }
}
```
