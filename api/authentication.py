from firebase_admin import auth
from rest_framework import authentication
from rest_framework import exceptions
from django.contrib.auth.models import User
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class FirebaseAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION")
        if not auth_header or not auth_header.startswith("Firebase "):
            return None

        token = auth_header.split(" ")[1]
        
        try:
            decoded_token = auth.verify_id_token(
                token,
                check_revoked=True
            )
            
            logger.info(f"[FirebaseAuth] Token verified for user: {decoded_token.get('uid')}")
            
            try:
                user = User.objects.get(username=decoded_token.get("uid"))
                return (user, None)
            except User.DoesNotExist:
                user = User.objects.create_user(
                    username=decoded_token.get("uid"),
                    email=decoded_token.get("email", "")
                )
                logger.info(f"[FirebaseAuth] Created new user: {user.username}")
                return (user, None)

        except auth.RevokedIdTokenError:
            logger.error("Token has been revoked")
            raise exceptions.AuthenticationFailed('Token has been revoked')
            
        except auth.ExpiredIdTokenError:
            logger.error("Token has expired")
            raise exceptions.AuthenticationFailed('Token has expired')
            
        except auth.InvalidIdTokenError:
            logger.error("Invalid token")
            raise exceptions.AuthenticationFailed('Invalid token')
            
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return None