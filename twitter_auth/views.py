from django.shortcuts import render, redirect
from django.views import View
from api.models import TwitterServiceAccount, UserProfile
from .models import TwitterUserAuthorization
import tweepy
import logging
from django.conf import settings
import os

logger = logging.getLogger(__name__)

class AuthDashboardView(View):
    template_name = 'twitter_auth/auth_dashboard.html'
    
    def get(self, request):
        service_accounts = TwitterServiceAccount.objects.filter(is_active=True)
        auth_status = []
        
        for account in service_accounts:
            auth_status.append({
                'account': account,
                'api_key': account.api_key,
                'is_active': account.is_active
            })
            
        return render(request, self.template_name, {
            'auth_status': auth_status
        })

class TwitterAuthView(View):
    def get(self, request, account_id):
        try:
            service_account = TwitterServiceAccount.objects.get(id=account_id)
            
            auth = tweepy.OAuthHandler(
                service_account.api_key,
                service_account.api_secret,
                os.getenv('TWITTER_SERVICE_CALLBACK_URL')
            )
            
            redirect_url = auth.get_authorization_url()
            request.session['request_token'] = auth.request_token
            request.session['service_account_id'] = account_id
            
            logger.info(f"""
                Starting Twitter OAuth for service account:
                Service Account: {account_id}
                Request Token: {auth.request_token}
            """)
            
            return redirect(redirect_url)
            
        except Exception as e:
            logger.error(f"Error in TwitterAuthView: {str(e)}")
            return redirect('auth_dashboard')

class TwitterServiceCallbackView(View):
    def get(self, request):
        verifier = request.GET.get('oauth_verifier')
        request_token = request.session.get('request_token')
        account_id = request.session.get('service_account_id')
        
        logger.info(f"""
            Received service callback:
            Verifier: {verifier}
            Account ID: {account_id}
            Request Token: {request_token}
        """)
        
        if not all([verifier, request_token, account_id]):
            logger.error("Missing required parameters in service callback")
            return redirect('auth_dashboard')
            
        try:
            service_account = TwitterServiceAccount.objects.get(id=account_id)
            
            auth = tweepy.OAuthHandler(
                service_account.api_key,
                service_account.api_secret
            )
            auth.request_token = request_token
            
            # Получаем access token
            auth.get_access_token(verifier)
            
            # Получаем информацию о Twitter пользователе
            api = tweepy.API(auth)
            twitter_user = api.verify_credentials()
            
            # Находим или создаем UserProfile
            user_profile, created = UserProfile.objects.get_or_create(
                twitter_account=twitter_user.screen_name,
                defaults={'status': 'ACTIVE'}
            )
            
            # Сохраняем авторизацию
            auth_record, auth_created = TwitterUserAuthorization.objects.update_or_create(
                user_profile=user_profile,
                service_account=service_account,
                defaults={
                    'oauth_token': auth.access_token,
                    'oauth_token_secret': auth.access_token_secret
                }
            )
            
            logger.info(f"""
                Service authorization successful:
                Twitter Account: {twitter_user.screen_name}
                Service Account: {service_account.id}
                UserProfile: {user_profile.id}
                Action: {'Created' if auth_created else 'Updated'}
            """)
            
            # Очищаем сессию
            request.session.pop('request_token', None)
            request.session.pop('service_account_id', None)
            
            return redirect('auth_dashboard')
            
        except Exception as e:
            logger.error(f"Error in service callback: {str(e)}")
            return redirect('auth_dashboard')
