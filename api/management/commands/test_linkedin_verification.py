from django.core.management.base import BaseCommand
from django.db.models import Q
from api.models import UserSocialProfile, SocialNetwork
from api.helpers.linkedin_helper import verify_linkedin_profile_by_url
import json


class Command(BaseCommand):
    help = 'Test LinkedIn profile verification using Apify'

    def add_arguments(self, parser):
        parser.add_argument(
            '--profile-url',
            type=str,
            help='LinkedIn profile URL to test (optional, will use first LinkedIn profile from DB if not provided)',
        )
        parser.add_argument(
            '--profile-id',
            type=int,
            help='UserSocialProfile ID to test (optional)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== LinkedIn Profile Verification Test ===\n'))
        
        profile_url = options.get('profile_url')
        profile_id = options.get('profile_id')
        
        # Если не указан URL, ищем LinkedIn профиль в базе
        if not profile_url and not profile_id:
            try:
                linkedin_network = SocialNetwork.objects.get(code='LINKEDIN')
                linkedin_profile = UserSocialProfile.objects.filter(
                    social_network=linkedin_network
                ).exclude(
                    Q(profile_url__isnull=True) | Q(profile_url='')
                ).first()
                
                if linkedin_profile:
                    profile_url = linkedin_profile.profile_url
                    profile_id = linkedin_profile.id
                    self.stdout.write(self.style.WARNING(
                        f'Found LinkedIn profile in DB:\n'
                        f'  ID: {linkedin_profile.id}\n'
                        f'  User: {linkedin_profile.user.username} (ID: {linkedin_profile.user.id})\n'
                        f'  Profile URL: {linkedin_profile.profile_url}\n'
                        f'  Current Status: {linkedin_profile.verification_status}\n'
                        f'  Is Verified: {linkedin_profile.is_verified}\n'
                    ))
                else:
                    self.stdout.write(self.style.ERROR(
                        'No LinkedIn profiles found in database. Please provide --profile-url or --profile-id'
                    ))
                    return
            except SocialNetwork.DoesNotExist:
                self.stdout.write(self.style.ERROR('LinkedIn social network not found in database'))
                return
        
        # Если указан profile_id, получаем URL из базы
        if profile_id and not profile_url:
            try:
                profile = UserSocialProfile.objects.get(id=profile_id)
                if profile.social_network.code != 'LINKEDIN':
                    self.stdout.write(self.style.ERROR(f'Profile {profile_id} is not a LinkedIn profile'))
                    return
                profile_url = profile.profile_url
                self.stdout.write(self.style.WARNING(
                    f'Using profile from DB:\n'
                    f'  ID: {profile.id}\n'
                    f'  User: {profile.user.username}\n'
                    f'  Profile URL: {profile.profile_url}\n'
                ))
            except UserSocialProfile.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Profile with ID {profile_id} not found'))
                return
        
        if not profile_url:
            self.stdout.write(self.style.ERROR('No profile URL provided'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'\nTesting verification for: {profile_url}\n'))
        self.stdout.write('Fetching profile data from Apify...\n')
        
        # Выполняем верификацию
        is_valid, profile_data, validation_result = verify_linkedin_profile_by_url(profile_url.strip())
        
        # Выводим результаты
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(self.style.SUCCESS('VERIFICATION RESULTS'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        
        if is_valid:
            self.stdout.write(self.style.SUCCESS('\n✅ PROFILE VERIFICATION PASSED\n'))
        else:
            self.stdout.write(self.style.ERROR('\n❌ PROFILE VERIFICATION FAILED\n'))
        
        # Выводим детали валидации
        self.stdout.write('\n--- Validation Details ---\n')
        failed_criteria = validation_result.get('failed_criteria', [])
        details = validation_result.get('details', {})
        
        if failed_criteria:
            self.stdout.write(self.style.ERROR(f'Failed Criteria: {", ".join(failed_criteria)}\n'))
        else:
            self.stdout.write(self.style.SUCCESS('All criteria passed!\n'))
        
        # Детальная информация
        self.stdout.write('\n--- Profile Details ---\n')
        
        if profile_data:
            self.stdout.write(f'Full Name: {profile_data.get("fullName", "N/A")}\n')
            self.stdout.write(f'Headline: {profile_data.get("headline", "N/A")}\n')
            self.stdout.write(f'Connections: {profile_data.get("connections", 0) or 0}\n')
            self.stdout.write(f'Followers: {profile_data.get("followers", 0) or 0}\n')
            self.stdout.write(f'Total (Connections + Followers): {details.get("total_connections_followers", 0)}\n')
            self.stdout.write(f'Has Avatar: {details.get("has_avatar", False)}\n')
            self.stdout.write(f'Has Description: {details.get("has_description", False)}\n')
            self.stdout.write(f'Has Emoji Fingerprint: {details.get("has_emoji_fingerprint", False)}\n')
            self.stdout.write(f'Has Work Experience: {details.get("has_work_experience", False)}\n')
            self.stdout.write(f'Experiences Count: {details.get("experiences_count", 0)}\n')
            
            if profile_data.get('about'):
                self.stdout.write(f'\nAbout:\n{profile_data.get("about")[:200]}...\n')
            
            if profile_data.get('experiences'):
                self.stdout.write(f'\nWork Experiences ({len(profile_data.get("experiences", []))}):\n')
                for i, exp in enumerate(profile_data.get('experiences', [])[:3], 1):
                    self.stdout.write(f'  {i}. {exp.get("title", "N/A")} at {exp.get("companyName", "N/A")}\n')
        else:
            self.stdout.write(self.style.ERROR('No profile data received from Apify\n'))
        
        # Критерии проверки
        self.stdout.write('\n--- Criteria Check ---\n')
        criteria_checks = [
            ('Minimum 100 connections or followers', 
             details.get('total_connections_followers', 0) >= 100,
             f"Got: {details.get('total_connections_followers', 0)}"),
            ('Profile has avatar', 
             details.get('has_avatar', False),
             ''),
            ('Clear profile description', 
             details.get('has_description', False),
             ''),
            ('Emoji fingerprint present', 
             details.get('has_emoji_fingerprint', False),
             f"Required: {', '.join(details.get('required_emojis', []))}"),
            ('Has at least 1 place of work', 
             details.get('has_work_experience', False),
             f"Got: {details.get('experiences_count', 0)}"),
        ]
        
        for criterion, passed, info in criteria_checks:
            status = '✅' if passed else '❌'
            status_style = self.style.SUCCESS if passed else self.style.ERROR
            info_text = f' ({info})' if info else ''
            self.stdout.write(f'{status} {criterion}{info_text}\n')
        
        # Выводим полный JSON результат
        self.stdout.write('\n--- Full Validation Result (JSON) ---\n')
        result_json = {
            'is_valid': is_valid,
            'failed_criteria': failed_criteria,
            'details': details,
            'profile_data_summary': {
                'fullName': profile_data.get('fullName') if profile_data else None,
                'headline': profile_data.get('headline') if profile_data else None,
                'connections': profile_data.get('connections') if profile_data else None,
                'followers': profile_data.get('followers') if profile_data else None,
            } if profile_data else None
        }
        self.stdout.write(json.dumps(result_json, indent=2, ensure_ascii=False))
        self.stdout.write('\n')
        
        # Выводим полные данные от Apify (первые 2000 символов)
        if profile_data:
            self.stdout.write('\n--- Full Apify Response (first 2000 chars) ---\n')
            full_data_str = json.dumps(profile_data, indent=2, ensure_ascii=False)
            self.stdout.write(full_data_str[:2000])
            if len(full_data_str) > 2000:
                self.stdout.write(f'\n... (truncated, total length: {len(full_data_str)} chars)\n')
            self.stdout.write('\n')
        
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('Test completed!'))
        self.stdout.write(self.style.SUCCESS('=' * 80 + '\n'))

