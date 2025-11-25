from django.core.management.base import BaseCommand
from api.helpers.linkedin_helper import verify_linkedin_profile
import json


class Command(BaseCommand):
    help = 'Test LinkedIn profile verification with mock data'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== LinkedIn Profile Verification Test (Mock Data) ===\n'))
        
        # Используем данные из примера пользователя
        mock_profile_data = {
            "linkedinUrl": "https://www.linkedin.com/in/ignalex/",
            "firstName": "Alex",
            "lastName": "Ign",
            "fullName": "Alex Ign",
            "headline": "Ai Product Engineer 🙃😄🤩🤖😛",
            "connections": 693,
            "followers": 848,
            "email": None,
            "mobileNumber": None,
            "jobTitle": "Ai Product Engineer",
            "jobStartedOn": "2023",
            "jobLocation": "Tallinn, Harjumaa, Estonia",
            "jobStillWorking": True,
            "companyName": "Askpot",
            "companyIndustry": "Technology, Information and Internet",
            "companyWebsite": "https://askpot.com",
            "companyLinkedin": "https://www.linkedin.com/company/askpot/",
            "companyFoundedIn": None,
            "companySize": "2-10",
            "currentJobDuration": None,
            "currentJobDurationInYrs": None,
            "topSkillsByEndorsements": None,
            "addressCountryOnly": "Estonia",
            "addressWithCountry": "Tallinn, Harjumaa Estonia",
            "addressWithoutCountry": "Tallinn, Harjumaa",
            "profilePic": "https://media.licdn.com/dms/image/v2/D5603AQEgf2wc547yog/profile-displayphoto-shrink_800_800/B56ZYyQ_rmH0Ag-/0/1744600039901?e=1765411200&v=beta&t=CaGOHKfg8Fpc03H7jMpFPUJoYlcuKkh7pOvr1WxUmB0",
            "profilePicHighQuality": "https://media.licdn.com/dms/image/v2/D5603AQEgf2wc547yog/profile-displayphoto-shrink_800_800/B56ZYyQ_rmH0Ag-/0/1744600039901?e=1765411200&v=beta&t=CaGOHKfg8Fpc03H7jMpFPUJoYlcuKkh7pOvr1WxUmB0",
            "backgroundPic": "https://media.licdn.com/dms/image/v2/D5616AQERSfTdVNyAcA/profile-displaybackgroundimage-shrink_350_1400/profile-displaybackgroundimage-shrink_350_1400/0/1721799055919?e=1765411200&v=beta&t=JTvzLTIPQP7tA__FcD9X-l6gPtVGZt3adlFiP_pj9bs",
            "linkedinId": "98136762",
            "isPremium": False,
            "isVerified": False,
            "isJobSeeker": False,
            "isRetired": False,
            "isCreator": False,
            "isInfluencer": False,
            "about": "If you can write an understandable PRD for your development team, you can be an AI Engineer using AI tools.\n\n🙃😄🤩🤖😛",
            "publicIdentifier": "ignalex",
            "linkedinPublicUrl": "https://linkedin.com/in/ignalex",
            "openConnection": False,
            "urn": "ACoAAAXZcroBAqXOQIW7YJJ6Vu-YPiiMK5fXXq4",
            "birthday": {
                "day": "",
                "month": "",
                "year": ""
            },
            "associatedHashtag": [],
            "experiences": [
                {
                    "companyId": "99532938",
                    "companyUrn": "urn:li:fsd_company:99532938",
                    "companyLink1": "https://www.linkedin.com/company/askpot/",
                    "companyName": "Askpot",
                    "companySize": "2-10",
                    "companyWebsite": "https://askpot.com",
                    "companyIndustry": "Technology, Information and Internet",
                    "logo": "https://media.licdn.com/dms/image/v2/D4E0BAQHDAZ0EFjDovw/company-logo_400_400/company-logo_400_400/0/1696874362722?e=1765411200&v=beta&t=6B2x46FMSVQeBjkBYAymUlxKRGpfiMb0PIDAAPNnhGk",
                    "title": "Ai Product Engineer",
                    "jobDescription": "🏆 Key Results:\n1️⃣ Triple MRR & ARR YoY\n2️⃣ Grow user database from 0 to 8K in less than one year\n3️⃣ Achieve 50%+ year-over-year revenue growth\n4️⃣ Launch an AI-based product 100% developed by AI",
                    "jobStartedOn": "2023",
                    "jobEndedOn": None,
                    "jobLocation": "Tallinn, Harjumaa, Estonia",
                    "jobStillWorking": True,
                    "jobLocationCountry": "US",
                    "employmentType": "Full-time",
                    "subtitle": None,
                    "caption": None,
                    "metadata": None
                }
            ],
            "updates": [],
            "skills": [],
            "creatorWebsite": [],
            "profilePicAllDimensions": [],
            "educations": [],
            "licenseAndCertificates": [],
            "honorsAndAwards": [],
            "languages": [],
            "volunteerAndAwards": [],
            "verifications": [],
            "promos": [],
            "highlights": [],
            "projects": [],
            "publications": [],
            "patents": [],
            "courses": [],
            "testScores": [],
            "organizations": [],
            "volunteerCauses": [],
            "interests": [],
            "recommendationsReceived": [],
            "recommendations": [],
            "peopleAlsoViewed": []
        }
        
        self.stdout.write(self.style.SUCCESS(f'Testing verification with mock profile data:\n'))
        self.stdout.write(f'  Profile: {mock_profile_data["fullName"]}\n')
        self.stdout.write(f'  Headline: {mock_profile_data["headline"]}\n')
        self.stdout.write(f'  Connections: {mock_profile_data["connections"]}\n')
        self.stdout.write(f'  Followers: {mock_profile_data["followers"]}\n')
        self.stdout.write(f'  Experiences: {len(mock_profile_data["experiences"])}\n\n')
        
        # Выполняем верификацию
        is_valid, validation_result = verify_linkedin_profile(mock_profile_data)
        
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
        self.stdout.write(f'Full Name: {mock_profile_data.get("fullName", "N/A")}\n')
        self.stdout.write(f'Headline: {mock_profile_data.get("headline", "N/A")}\n')
        self.stdout.write(f'Connections: {mock_profile_data.get("connections", 0) or 0}\n')
        self.stdout.write(f'Followers: {mock_profile_data.get("followers", 0) or 0}\n')
        self.stdout.write(f'Total (Connections + Followers): {details.get("total_connections_followers", 0)}\n')
        self.stdout.write(f'Has Avatar: {details.get("has_avatar", False)}\n')
        self.stdout.write(f'Has Description: {details.get("has_description", False)}\n')
        self.stdout.write(f'Has Emoji Fingerprint: {details.get("has_emoji_fingerprint", False)}\n')
        self.stdout.write(f'Has Work Experience: {details.get("has_work_experience", False)}\n')
        self.stdout.write(f'Experiences Count: {details.get("experiences_count", 0)}\n')
        
        if mock_profile_data.get('about'):
            self.stdout.write(f'\nAbout:\n{mock_profile_data.get("about")[:200]}...\n')
        
        if mock_profile_data.get('experiences'):
            self.stdout.write(f'\nWork Experiences ({len(mock_profile_data.get("experiences", []))}):\n')
            for i, exp in enumerate(mock_profile_data.get('experiences', [])[:3], 1):
                self.stdout.write(f'  {i}. {exp.get("title", "N/A")} at {exp.get("companyName", "N/A")}\n')
        
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
            'details': details
        }
        self.stdout.write(json.dumps(result_json, indent=2, ensure_ascii=False))
        self.stdout.write('\n')
        
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('Test completed!'))
        self.stdout.write(self.style.SUCCESS('=' * 80 + '\n'))

