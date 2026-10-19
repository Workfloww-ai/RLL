import json
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from backend.core.config import settings
from backend.core.crypto import encrypt_payload, decrypt_payload
import logging

logger = logging.getLogger(__name__)

class EncryptedRoute(APIRoute):
    def get_route_handler(self):
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            # Only intercept specific sensitive paths to avoid CPU overhead on large master data
            sensitive_paths = ["/login", "/reset-password", "/forgot-password", "/users", "/settings", "/system", "/log-error"]
            is_sensitive = any(p in request.url.path for p in sensitive_paths)
            
            was_encrypted = False
            if is_sensitive and settings.PAYLOAD_ENCRYPTION_KEY:
                # Intercept request and decrypt body
                try:
                    body = await request.body()
                    if body:
                        payload = json.loads(body)
                        if isinstance(payload, dict) and "encrypted_data" in payload:
                            was_encrypted = True
                            decrypted_str = decrypt_payload(payload["encrypted_data"], settings.PAYLOAD_ENCRYPTION_KEY)
                            # Overwrite the cached body and json so FastAPI parses the decrypted payload
                            request._body = decrypted_str.encode('utf-8')
                            request._json = json.loads(decrypted_str)
                except Exception as e:
                    logger.error(f"Failed to decrypt payload: {str(e)}")
                    return JSONResponse(status_code=400, content={"detail": "Failed to decrypt request payload."})
            
            # Call original route handler
            response = await original_route_handler(request)
            
            # Intercept response and encrypt body if production or client requested encryption
            should_encrypt_response = is_sensitive and settings.PAYLOAD_ENCRYPTION_KEY and (was_encrypted or settings.ENVIRONMENT == "production")
            if should_encrypt_response:
                if isinstance(response, Response) and response.body:
                    try:
                        if response.media_type == "application/json":
                            body_str = response.body.decode('utf-8')
                            encrypted_str = encrypt_payload(body_str, settings.PAYLOAD_ENCRYPTION_KEY)
                            new_body = json.dumps({"encrypted_data": encrypted_str}).encode('utf-8')
                            response.body = new_body
                            response.headers["Content-Length"] = str(len(new_body))
                    except Exception as e:
                        logger.error(f"Failed to encrypt payload: {str(e)}")
                        return JSONResponse(status_code=500, content={"detail": "Failed to encrypt response payload."})
                        
            return response

        return custom_route_handler
