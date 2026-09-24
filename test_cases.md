# Task 1 Swagger test sequence

Run the app on port 8000 and open `http://127.0.0.1:8000/docs`.

1. POST `/items`
```json
{
  "title": "Black Wallet",
  "description": "Black leather wallet found near the library entrance.",
  "category": "Accessories",
  "location": "Central Library",
  "reported_by": "Rahul Sharma",
  "status": "Found"
}
```
2. POST another item with status `Lost` and category `Electronics`.
3. GET `/items`.
4. GET `/items/1`.
5. PUT `/items/1` with `{"status":"Returned"}`.
6. GET `/items/status/Returned`.
7. GET `/items/category/Accessories`.
8. DELETE `/items/1`.
9. GET `/items/9999` to show HTTP 404.
10. POST an invalid item using `"status":"Missing"` to show HTTP 422 validation.
