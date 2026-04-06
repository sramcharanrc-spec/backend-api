def success_response(data=None, message="SUCCESS"):
    return {
        "status": "SUCCESS",
        "message": message,
        "data": data
    }