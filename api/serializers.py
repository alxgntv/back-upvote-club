from rest_framework import serializers
from .models import UserProfile, Task, TaskCompletion, InviteCode, SocialNetwork, UserSocialProfile, BlogPost, PostCategory, PostTag, TaskReport, ActionType, ActionLanding, PaymentTransaction, Withdrawal, OnboardingProgress, Review, BuyLanding
from django.utils import timezone
import logging
from django.utils.dateparse import parse_datetime
from django.db.models import Exists, OuterRef, Sum
from django.db import connection
from django.db import transaction

logger = logging.getLogger(__name__)

class SocialNetworkSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialNetwork
        fields = ['id', 'name', 'code', 'icon', 'is_active', 'created_at']

class TaskCompletionSerializer(serializers.ModelSerializer):
    social_data = serializers.SerializerMethodField()
    username = serializers.SerializerMethodField()
    user_id = serializers.IntegerField(source='user.id')

    class Meta:
        model = TaskCompletion
        fields = [
            'id',
            'user_id',
            'username',
            'action',
            'created_at',
            'completed_at',
            'post_url',
            'social_data',
            'metadata'
        ]

    def get_username(self, obj):
        try:
            social_profile = obj.user.social_profiles.filter(social_network=obj.task.social_network).first()
            if social_profile:
                return social_profile.username
            return obj.user.username
        except Exception as e:
            print(f"Error getting username: {str(e)}")
            return obj.user.username

    def get_social_data(self, obj):
        try:
            social_profile = obj.user.social_profiles.filter(social_network=obj.task.social_network).first()
            # Получаем firebase-аватарку пользователя (если есть)
            firebase_avatar = None
            if hasattr(obj.user, 'avatar_url') and obj.user.avatar_url:
                firebase_avatar = obj.user.avatar_url
            # Если firebase-аватарки нет, используем social_profile.avatar_url (старое поведение)
            avatar_url = firebase_avatar or (social_profile.avatar_url if social_profile else None)
            if social_profile:
                return {
                    'username': social_profile.username,
                    'avatar_url': avatar_url,
                    'profile_url': social_profile.profile_url
                }
            # Если social_profile нет, возвращаем username из user и avatar_url (firebase или None)
            return {
                'username': obj.user.username,
                'avatar_url': avatar_url,
                'profile_url': None
            }
        except Exception as e:
            print(f"Error getting social data: {str(e)}")
            return None

class TaskSerializer(serializers.ModelSerializer):
    creator_id = serializers.IntegerField(source='creator.id', read_only=True)
    completions = TaskCompletionSerializer(many=True, read_only=True)
    social_network = SocialNetworkSerializer(read_only=True)
    social_network_code = serializers.CharField(write_only=True)
    is_pinned = serializers.BooleanField(default=False)
    my_review = serializers.SerializerMethodField(read_only=True)
    has_review = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Task
        fields = '__all__'  # чтобы is_pinned точно был в выдаче
        read_only_fields = [
            'id', 
            'actions_completed', 
            'status', 
            'created_at',
            'original_price',
            'creator',
            'my_review',
            'has_review',
        ]

    def validate_meaningful_comments(self, value):
        if value is None:
            return value
        if not isinstance(value, list):
            raise serializers.ValidationError('Must be a JSON array of comments')
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError('Each item must be an object {id, text, sent}')
            if 'id' not in item or 'text' not in item or 'sent' not in item:
                raise serializers.ValidationError('Each comment must have id, text and sent fields')
            if not isinstance(item['sent'], bool):
                raise serializers.ValidationError('Field "sent" must be boolean')
            if not isinstance(item['text'], str) or not item['text']:
                raise serializers.ValidationError('Field "text" must be non-empty string')
        return value

    def create(self, validated_data):
        # social_network уже установлен в validate, просто удаляем social_network_code
        validated_data.pop('social_network_code', None)
        
        # Создаем Task
        return super().create(validated_data)

    def validate(self, data):
        social_network_code = data.get('social_network_code')
        task_type = data.get('type')
        post_url = data.get('post_url')
        price = data.get('price')
        actions_required = data.get('actions_required')

        if not price:
            raise serializers.ValidationError("Price is required")
            
        if not actions_required:
            raise serializers.ValidationError("Actions required is required")

        try:
            social_network = SocialNetwork.objects.get(code=social_network_code)
            # Добавляем social_network в data для создания Task
            data['social_network'] = social_network
        except SocialNetwork.DoesNotExist:
            raise serializers.ValidationError(f"Social network with code {social_network_code} not found")

        if not task_type:
            raise serializers.ValidationError("Task type is required")

        if not post_url:
            raise serializers.ValidationError("Post URL is required")

        if not social_network.available_actions.filter(code=task_type).exists():
            raise serializers.ValidationError(f"Action type {task_type} is not available for {social_network.name}")

        # Проверка URL в зависимости от социальной сети
        if social_network.code == 'TWITTER':
            if not ('twitter.com' in post_url or 'x.com' in post_url):
                raise serializers.ValidationError("Invalid Twitter URL format")
        elif social_network.code == 'LINKEDIN':
            if not 'linkedin.com' in post_url:
                raise serializers.ValidationError("Invalid LinkedIn URL format")
        elif social_network.code == 'GITHUB':
            if not 'github.com' in post_url:
                raise serializers.ValidationError("Invalid GitHub URL format")
        elif social_network.code == 'REDDIT':
            if not 'reddit.com' in post_url:
                raise serializers.ValidationError("Invalid Reddit URL format")
        elif social_network.code == 'DEVTO':
            if not 'dev.to' in post_url:
                raise serializers.ValidationError("Invalid Dev.to URL format")
        elif social_network.code == 'MEDIUM':
            if not 'medium.com' in post_url:
                raise serializers.ValidationError("Invalid Medium URL format")
        elif social_network.code == 'PRODUCTHUNT':
            if not 'producthunt.com' in post_url:
                raise serializers.ValidationError("Invalid Product Hunt URL format")
        elif social_network.code == 'HACKERNEWS':
            if not 'news.ycombinator.com' in post_url:
                raise serializers.ValidationError("Invalid Hacker News URL format")
        elif social_network.code == 'INDIEHACKERS':
            if not 'indiehackers.com' in post_url:
                raise serializers.ValidationError("Invalid Indie Hackers URL format")
        
        # Валидация meaningful_comment для типа COMMENT
        meaningful_comment = data.get('meaningful_comment')
        meaningful_comments = data.get('meaningful_comments')
        if task_type == 'COMMENT':
            if meaningful_comment:
                # meaningful_comments обязателен и список не пуст
                if not meaningful_comments or not isinstance(meaningful_comments, list) or len(meaningful_comments) == 0:
                    raise serializers.ValidationError('Meaningful comments list is required and must be a non-empty array when Meaningful comment is enabled')
                # уже прошли через validate_meaningful_comments при сериализации поля
        else:
            # для других типов обнулим meaningful-флаги
            data['meaningful_comment'] = False
            data['meaningful_comments'] = None

        return data

    def get_my_review(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        if not user or not user.is_authenticated:
            return None
        from .models import Review
        review = Review.objects.filter(user=user, task=obj).first()
        if review:
            return ReviewSerializer(review).data
        return None

    def get_has_review(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        if not user or not user.is_authenticated:
            return False
        from .models import Review
        return Review.objects.filter(user=user, task=obj).exists()

class UserProfileSerializer(serializers.ModelSerializer):
    daily_task_limit = serializers.SerializerMethodField()
    active_invite_code = serializers.SerializerMethodField()
    discount_rate = serializers.SerializerMethodField()
    available_tasks_for_completion = serializers.SerializerMethodField()
    potential_earnings = serializers.SerializerMethodField()
    social_profiles = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            'id', 'user', 'balance', 
            'status',
            'available_invites',
            'trial_start_date', 'invite_code', 'available_tasks',
            'daily_task_limit', 'completed_tasks_count', 
            'active_invite_code', 'discount_rate',
            'available_tasks_for_completion', 'potential_earnings',
            'game_rewards_claimed', 'last_reward_at_task_count',
            'bonus_tasks_completed', 'country_code', 'chosen_country',
            'paypal_address',
            'social_profiles',
            'referrer_url', 'landing_url', 'referrer_timestamp', 'referrer_user_agent',
            'device_type', 'os_name', 'os_version',
        ]

    def get_daily_task_limit(self, obj):
        return obj.get_daily_task_limit()

    def get_available_tasks_for_completion(self, obj):
        """Возвращает количество доступных для выполнения заданий с учетом всех фильтров"""
        # Используем тот же SQL запрос, что и в TaskViewSet
        with connection.cursor() as cursor:
            cursor.execute("""
                WITH CompletedCombinations AS (
                    SELECT DISTINCT t.post_url, t.type, t.social_network_id
                    FROM api_taskcompletion tc
                    JOIN api_task t ON tc.task_id = t.id
                    WHERE tc.user_id = %s
                ),
                RankedTasks AS (
                    SELECT 
                        t.id,
                        ROW_NUMBER() OVER (
                            PARTITION BY t.post_url, t.type, t.social_network_id
                            ORDER BY t.price DESC, t.created_at DESC
                        ) as rn
                    FROM api_task t
                    WHERE t.status = 'ACTIVE' 
                    AND t.creator_id != %s
                    AND NOT EXISTS (
                        SELECT 1 
                        FROM CompletedCombinations cc
                        WHERE cc.post_url = t.post_url 
                        AND cc.type = t.type
                        AND cc.social_network_id = t.social_network_id
                    )
                    AND NOT EXISTS (
                        SELECT 1 
                        FROM api_taskreport tr
                        WHERE tr.task_id = t.id 
                        AND tr.user_id = %s
                    )
                )
                SELECT COUNT(*) FROM RankedTasks WHERE rn = 1
            """, [obj.user.id, obj.user.id, obj.user.id])
            
            count = cursor.fetchone()[0]
            
            logger.info(f"""
                [get_available_tasks_for_completion] Counting available tasks for user {obj.user.id}:
                - Total count: {count}
                - SQL params: user_id={obj.user.id}
            """)
            
        return count

    def get_potential_earnings(self, obj):
        return obj.get_potential_earnings()

    def get_active_invite_code(self, obj):
        invite = InviteCode.objects.filter(
            creator=obj.user,
            status='ACTIVE'
        ).first()
        
        if invite:
            return {
                'code': invite.code,
            }
        return None

    def get_discount_rate(self, obj):
        """Возвращает процент скидки для текущего статуса"""
        logger.info(f"Getting discount rate for user {obj.user.username} with status {obj.status}")
        return obj.get_discount_rate()

    def get_social_profiles(self, obj):
        profiles = obj.user.social_profiles.all()
        # Формируем словарь: {"TWITTER": "PENDING", ...}
        return {p.social_network.code: p.verification_status for p in profiles}

class InviteCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = InviteCode
        fields = ['code', 'status', 'max_uses', 'uses_count']

class UserSocialProfileSerializer(serializers.ModelSerializer):
    social_network = SocialNetworkSerializer(read_only=True)
    user = serializers.SerializerMethodField()

    class Meta:
        model = UserSocialProfile
        fields = [
            # Основные данные
            'id', 
            'user',
            'social_network',
            'social_id',
            'username',
            'profile_url',
            'avatar_url',
            
            # Статус верификации
            'is_verified',
            'verification_status',
            'verification_date',
            
            # OAuth данные (скрыты)
            # 'oauth_token',
            # 'oauth_token_secret',
            
            # Метрики профиля
            'followers_count',
            'following_count',
            'posts_count',
            'account_created_at',
            
            # Системные поля
            'created_at',
            'updated_at',
            'last_sync_at'
        ]
        extra_kwargs = {
            'oauth_token': {'write_only': True},
            'oauth_token_secret': {'write_only': True}
        }

    def get_user(self, obj):
        """Возвращает основную информацию о пользователе"""
        return {
            'id': obj.user.id,
            'username': obj.user.username,
            'email': obj.user.email
        }

    def to_representation(self, instance):
        """Добавляем дополнительное форматирование данных"""
        data = super().to_representation(instance)
        
        # Форматируем даты в удобный формат
        for field in ['verification_date', 'account_created_at', 'created_at', 'updated_at', 'last_sync_at']:
            if data.get(field):
                data[field] = timezone.localtime(parse_datetime(data[field])).strftime('%Y-%m-%d %H:%M:%S')
        
        # Добавляем человекочитаемые статусы
        status_map = {
            'NOT_VERIFIED': 'Not Verified',
            'PENDING': 'Pending Verification',
            'VERIFIED': 'Verified',
            'REJECTED': 'Rejected'
        }
        data['verification_status_display'] = status_map.get(data['verification_status'], data['verification_status'])
        
        # Добавляем метрики в удобном формате
        data['metrics'] = {
            'followers': data['followers_count'],
            'following': data['following_count'],
            'posts': data['posts_count']
        }
        
        logger.info(f"""Serializing social profile:
            User: {instance.user.username}
            Network: {instance.social_network.name}
            Username: {instance.username}
            Metrics: {data['metrics']}
        """)
        
        return data

class PostTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostTag
        fields = ['id', 'name', 'slug']

class PostCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PostCategory
        fields = ['id', 'name', 'slug']

class BlogPostSerializer(serializers.ModelSerializer):
    category = PostCategorySerializer(read_only=True)
    tags = PostTagSerializer(many=True, read_only=True)
    author_name = serializers.CharField(source='author.username', read_only=True)

    class Meta:
        model = BlogPost
        fields = [
            'id', 
            'title',
            'slug',
            'content',
            'image',
            'category',
            'tags',
            'author_name',
            'published_at'
        ]

class TaskReportSerializer(serializers.ModelSerializer):
    task_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = TaskReport
        fields = ('id', 'task', 'task_id', 'reason', 'details', 'created_at')
        read_only_fields = ('id', 'created_at', 'task')

    def validate(self, data):
        if 'task_id' in data:
            data['task'] = data.pop('task_id')
        return data

class ActionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActionType
        fields = ['id', 'name', 'code', 'name_plural']

class SocialNetworkWithActionsSerializer(serializers.ModelSerializer):
    available_actions = ActionTypeSerializer(many=True, read_only=True)
    
    class Meta:
        model = SocialNetwork
        fields = ['id', 'name', 'code', 'available_actions']

class ActionLandingSerializer(serializers.ModelSerializer):
    full_slug = serializers.SerializerMethodField()

    class Meta:
        model = ActionLanding
        fields = '__all__'
        # full_slug будет добавлен автоматически

    def get_full_slug(self, obj):
        if not obj.social_network:
            return f"/{obj.slug}"
        sn_code = obj.social_network.code.lower()
        if not obj.action:
            # Родительский лендинг соцсети
            if obj.slug == sn_code:
                return f"/{sn_code}"
            return f"/{sn_code}/{obj.slug}"
        action_code = obj.action.lower()
        expected_slug = f"{sn_code}-{action_code}"
        if obj.slug == expected_slug:
            # Экшеновый лендинг
            return f"/{sn_code}/{action_code}"
        # Обычный лендинг
        return f"/{sn_code}/{action_code}/{obj.slug}"

class BuyLandingSerializer(serializers.ModelSerializer):
    social_network = SocialNetworkSerializer(read_only=True)
    action = ActionTypeSerializer(read_only=True)
    social_network_id = serializers.IntegerField(write_only=True, required=False)
    action_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = BuyLanding
        fields = [
            'id',
            'title',
            'h1',
            'description',
            'short_description',
            'social_network',
            'social_network_id',
            'action',
            'action_id',
            'slug',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class InvitedUserSerializer(serializers.ModelSerializer):
    firebase_uid = serializers.CharField(source='user.username')  # Firebase UID хранится в username
    registration_date = serializers.DateTimeField(source='user.date_joined')
    completed_tasks = serializers.IntegerField(source='completed_tasks_count')
    total_spent = serializers.SerializerMethodField()
    potential_earnings = serializers.SerializerMethodField()
    
    class Meta:
        model = UserProfile
        fields = [
            'firebase_uid',
            'registration_date',
            'status',
            'completed_tasks',
            'total_spent',
            'potential_earnings'
        ]

    def get_total_spent(self, obj):
        """Подсчитываем общую сумму трат пользователя"""
        total = PaymentTransaction.objects.filter(
            user=obj.user,
            status='COMPLETED'
        ).aggregate(
            total=Sum('amount')
        )['total'] or 0
        
        return float(total)

    def get_potential_earnings(self, obj):
        """Считаем потенциальный доход (30% от общих трат)"""
        total_spent = self.get_total_spent(obj)
        return round(total_spent * 0.3, 2)

class CreateUserSocialProfileSerializer(serializers.ModelSerializer):
    social_network_code = serializers.CharField(write_only=True)
    profile_url = serializers.URLField(required=True)
    
    class Meta:
        model = UserSocialProfile
        fields = [
            'social_network_code',
            'profile_url'
        ]
        
    def validate(self, data):
        social_network_code = data.get('social_network_code')
        profile_url = data.get('profile_url')
        
        try:
            social_network = SocialNetwork.objects.get(code=social_network_code)
            data['social_network'] = social_network
        except SocialNetwork.DoesNotExist:
            raise serializers.ValidationError(f"Social network with code {social_network_code} not found")
            
        # Проверяем формат URL в зависимости от соц.сети
        if social_network.code == 'TWITTER':
            if not ('twitter.com' in profile_url or 'x.com' in profile_url):
                raise serializers.ValidationError("Invalid Twitter URL format")
        elif social_network.code == 'LINKEDIN':
            if not 'linkedin.com' in profile_url:
                raise serializers.ValidationError("Invalid LinkedIn URL format")
        elif social_network.code == 'GITHUB':
            if not 'github.com' in profile_url:
                raise serializers.ValidationError("Invalid GitHub URL format")
        elif social_network.code == 'REDDIT':
            if not 'reddit.com' in profile_url:
                raise serializers.ValidationError("Invalid Reddit URL format")
        elif social_network.code == 'DEVTO':
            if not 'dev.to' in profile_url:
                raise serializers.ValidationError("Invalid Dev.to URL format")
        elif social_network.code == 'MEDIUM':
            if not 'medium.com' in profile_url:
                raise serializers.ValidationError("Invalid Medium URL format")
        elif social_network.code == 'PRODUCTHUNT':
            if not 'producthunt.com' in profile_url:
                raise serializers.ValidationError("Invalid Product Hunt URL format")
        elif social_network.code == 'HACKERNEWS':
            if not 'news.ycombinator.com' in profile_url:
                raise serializers.ValidationError("Invalid Hacker News URL format")
        elif social_network.code == 'INDIEHACKERS':
            if not 'indiehackers.com' in profile_url:
                raise serializers.ValidationError("Invalid Indie Hackers URL format")
            
        return data

class BulkCreateUserSocialProfileSerializer(serializers.Serializer):
    profiles = serializers.ListField(
        child=serializers.DictField(
            child=serializers.CharField()
        ),
        min_length=1
    )
    
    def validate_profiles(self, profiles):
        validated_profiles = []
        for profile in profiles:
            social_network_code = profile.get('social_network_code')
            profile_url = profile.get('profile_url')
            
            if not social_network_code or not profile_url:
                raise serializers.ValidationError("Each profile must have social_network_code and profile_url")
                
            try:
                social_network = SocialNetwork.objects.get(code=social_network_code)
            except SocialNetwork.DoesNotExist:
                raise serializers.ValidationError(f"Social network with code {social_network_code} not found")
                
            # Извлекаем username из URL в зависимости от соц.сети
            if social_network.code == 'TWITTER':
                if not ('twitter.com' in profile_url or 'x.com' in profile_url):
                    raise serializers.ValidationError(f"Invalid Twitter URL format: {profile_url}")
                username = profile_url.split('/')[-1]
            elif social_network.code == 'LINKEDIN':
                if not 'linkedin.com' in profile_url:
                    raise serializers.ValidationError(f"Invalid LinkedIn URL format: {profile_url}")
                username = profile_url.split('/')[-1]
            elif social_network.code == 'GITHUB':
                if not 'github.com' in profile_url:
                    raise serializers.ValidationError(f"Invalid GitHub URL format: {profile_url}")
                username = profile_url.split('/')[-1]
            elif social_network.code == 'REDDIT':
                if not 'reddit.com' in profile_url:
                    raise serializers.ValidationError(f"Invalid Reddit URL format: {profile_url}")
                username = profile_url.split('/')[-1]
            elif social_network.code == 'DEVTO':
                if not 'dev.to' in profile_url:
                    raise serializers.ValidationError(f"Invalid Dev.to URL format: {profile_url}")
                username = profile_url.split('/')[-1]
            elif social_network.code == 'MEDIUM':
                if not 'medium.com' in profile_url:
                    raise serializers.ValidationError(f"Invalid Medium URL format: {profile_url}")
                username = profile_url.split('/')[-1]
            elif social_network.code == 'PRODUCTHUNT':
                if not 'producthunt.com' in profile_url:
                    raise serializers.ValidationError(f"Invalid Product Hunt URL format: {profile_url}")
                username = profile_url.split('/')[-1]
            elif social_network.code == 'HACKERNEWS':
                if not 'news.ycombinator.com' in profile_url:
                    raise serializers.ValidationError(f"Invalid Hacker News URL format: {profile_url}")
                username = profile_url.split('/')[-1]
            elif social_network.code == 'INDIEHACKERS':
                if not 'indiehackers.com' in profile_url:
                    raise serializers.ValidationError(f"Invalid Indie Hackers URL format: {profile_url}")
                username = profile_url.split('/')[-1]
                
            validated_profiles.append({
                'social_network': social_network,
                'username': username,
                'profile_url': profile_url
            })
            
        return validated_profiles

class WithdrawalSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    conversion_rate = serializers.FloatField(read_only=True)
    can_be_cancelled = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Withdrawal
        fields = [
            'id',
            'user',
            'user_name',
            'amount_usd',
            'points_sold',
            'withdrawal_method',
            'withdrawal_address',
            'status',
            'created_at',
            'updated_at',
            'processed_at',
            'transaction_id',
            'conversion_rate',
            'can_be_cancelled'
        ]
        read_only_fields = [
            'id',
            'user',
            'user_name',
            'status',
            'created_at',
            'updated_at',
            'processed_at',
            'transaction_id',
            'conversion_rate',
            'can_be_cancelled'
        ]

class CreateWithdrawalSerializer(serializers.ModelSerializer):
    """Сериализатор для создания нового withdrawal запроса"""
    
    class Meta:
        model = Withdrawal
        fields = [
            'amount_usd',
            'withdrawal_method',
            'withdrawal_address'
        ]
    
    def validate_amount_usd(self, value):
        """Проверяем минимальную сумму для вывода"""
        min_amount = Withdrawal.get_min_withdrawal_amount()
        if value < min_amount:
            raise serializers.ValidationError(
                f'Minimum withdrawal amount is ${min_amount:.2f}'
            )
        return value
    
    def validate_withdrawal_address(self, value):
        """Проверяем формат адреса в зависимости от метода"""
        withdrawal_method = self.initial_data.get('withdrawal_method')
        
        if withdrawal_method == 'PAYPAL':
            # Проверяем email формат для PayPal
            from django.core.validators import EmailValidator
            from django.core.exceptions import ValidationError as DjangoValidationError
            validator = EmailValidator()
            try:
                validator(value)
            except DjangoValidationError:
                raise serializers.ValidationError('Invalid PayPal email address format')
        
        elif withdrawal_method == 'USDT':
            # Проверяем формат USDT адреса (TRC20)
            if not value or len(value) < 20:
                raise serializers.ValidationError('Invalid USDT address format')
                
        return value
    
    def validate(self, data):
        """Дополнительная валидация данных"""
        from decimal import Decimal
        
        user = self.context['request'].user
        amount_usd = data['amount_usd']
        
        # Вычисляем необходимое количество поинтов (конвертируем в Decimal)
        conversion_rate = Decimal('0.01')  # 1 поинт = $0.01
        points_needed = int(amount_usd / conversion_rate)
        
        # Проверяем, хватает ли поинтов у пользователя
        user_profile = user.userprofile
        if user_profile.balance < points_needed:
            raise serializers.ValidationError(
                f'Insufficient balance. You need {points_needed} points '
                f'but have only {user_profile.balance} points.'
            )
        
        # Добавляем points_sold в validated_data
        data['points_sold'] = points_needed
        
        return data
    
    def create(self, validated_data):
        """Создаем withdrawal и списываем поинты"""
        user = self.context['request'].user
        points_sold = validated_data['points_sold']
        
        with transaction.atomic():
            # Проверяем баланс еще раз в транзакции
            user_profile = UserProfile.objects.select_for_update().get(user=user)
            
            if user_profile.balance < points_sold:
                raise serializers.ValidationError('Insufficient balance')
            
            # Списываем поинты
            user_profile.balance -= points_sold
            user_profile.save(update_fields=['balance'])
            
            # Создаем withdrawal
            withdrawal = Withdrawal.objects.create(
                user=user,
                **validated_data
            )
            
            logger.info(f"""
                [CreateWithdrawalSerializer] Created withdrawal:
                ID: {withdrawal.id}
                User: {user.username}
                Amount: ${withdrawal.amount_usd}
                Points Sold: {points_sold}
                Method: {withdrawal.withdrawal_method}
                Address: {withdrawal.withdrawal_address}
                New Balance: {user_profile.balance}
            """)
            
            # Отправляем email уведомление администратору
            try:
                from .utils.email_utils import send_withdrawal_notification_email
                email_sent = send_withdrawal_notification_email(withdrawal)
                if email_sent:
                    logger.info(f"[CreateWithdrawalSerializer] Email notification sent for withdrawal #{withdrawal.id}")
                else:
                    logger.warning(f"[CreateWithdrawalSerializer] Failed to send email notification for withdrawal #{withdrawal.id}")
            except Exception as e:
                logger.error(f"[CreateWithdrawalSerializer] Error sending email notification for withdrawal #{withdrawal.id}: {str(e)}")
            
            return withdrawal

class WithdrawalStatsSerializer(serializers.Serializer):
    """Сериализатор для статистики по выводам"""
    total_withdrawals = serializers.IntegerField()
    total_amount_usd = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_points_sold = serializers.IntegerField()
    pending_withdrawals = serializers.IntegerField()
    completed_withdrawals = serializers.IntegerField()
    min_withdrawal_amount = serializers.FloatField()
    conversion_rate = serializers.FloatField()
    points_needed_for_min_withdrawal = serializers.IntegerField()

class OnboardingProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = OnboardingProgress
        fields = [
            'id',
            'user',
            'chosen_country',
            'account_type',
            'social_networks',
            'actions',
            'goal_description',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def update(self, instance, validated_data):
        # Обновляем поля онбординга
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Синхронизируем выбранную страну с профилем пользователя
        if 'chosen_country' in validated_data:
            try:
                user_profile = instance.user.userprofile
                user_profile.chosen_country = validated_data.get('chosen_country')
                user_profile.save(update_fields=['chosen_country'])
            except Exception:
                pass
        return instance

    def create(self, validated_data):
        onboarding = OnboardingProgress.objects.create(**validated_data)

        # Синхронизируем выбранную страну с профилем пользователя при создании
        chosen_country_value = validated_data.get('chosen_country')
        if chosen_country_value is not None:
            try:
                user_profile = onboarding.user.userprofile
                user_profile.chosen_country = chosen_country_value
                user_profile.save(update_fields=['chosen_country'])
            except Exception:
                pass

        return onboarding

class ReviewSerializer(serializers.ModelSerializer):
    action_code = serializers.CharField(write_only=True, required=False)
    social_network_code = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = Review
        fields = [
            'id', 'user', 'social_network', 'action', 'actions_count', 'task',
            'rating', 'comment',
            'created_at', 'updated_at', 'action_code', 'social_network_code'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'user']
        extra_kwargs = {
            'social_network': {'required': False},
            'action': {'required': False},
        }

    def validate_rating(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError('Rating must be between 1 and 5')
        return value

    def validate(self, data):
        # Определяем, это создание или обновление
        is_create = self.instance is None
        
        # При создании action_code и social_network_code обязательны
        if is_create:
            if 'action_code' not in data:
                raise serializers.ValidationError({'action_code': 'This field is required when creating a review.'})
            if 'social_network_code' not in data:
                raise serializers.ValidationError({'social_network_code': 'This field is required when creating a review.'})
        
        # Если передан action_code, находим ActionType по коду
        if 'action_code' in data:
            from .models import ActionType
            try:
                action_type = ActionType.objects.get(code=data['action_code'].upper())
                data['action'] = action_type
            except ActionType.DoesNotExist:
                raise serializers.ValidationError(f"Action type with code '{data['action_code']}' not found")
            data.pop('action_code', None)
        
        # Если передан social_network_code, находим SocialNetwork по коду
        if 'social_network_code' in data:
            try:
                social_network = SocialNetwork.objects.get(code=data['social_network_code'].upper())
                data['social_network'] = social_network
            except SocialNetwork.DoesNotExist:
                raise serializers.ValidationError(f"Social network with code '{data['social_network_code']}' not found")
            data.pop('social_network_code', None)
        
        # При создании проверяем, что action и social_network установлены
        if is_create:
            if 'action' not in data:
                raise serializers.ValidationError({'action': 'This field is required.'})
            if 'social_network' not in data:
                raise serializers.ValidationError({'social_network': 'This field is required.'})
        
        return data

    def create(self, validated_data):
        # Устанавливаем пользователя из запроса
        validated_data['user'] = self.context['request'].user
        
        # Проверяем, не существует ли уже рейтинг для этой задачи от этого пользователя
        existing_review = Review.objects.filter(
            user=validated_data['user'],
            task=validated_data['task']
        ).first()
        
        if existing_review:
            # Если рейтинг уже существует, обновляем его
            for key, value in validated_data.items():
                if key != 'user':  # Не обновляем пользователя
                    setattr(existing_review, key, value)
            existing_review.save()
            return existing_review
        
        return super().create(validated_data)

class MedianSpeedResponseSerializer(serializers.Serializer):
    """Сериализатор для ответа API медианной скорости выполнения заданий"""
    social_network = serializers.CharField(help_text='Social network code')
    action = serializers.CharField(help_text='Action type code')
    actions_count = serializers.IntegerField(help_text='Number of actions required')
    median_speed_minutes = serializers.FloatField(help_text='Median completion speed in minutes')
    cached_at = serializers.DateTimeField(help_text='When the result was cached')
    cache_expires_in = serializers.CharField(help_text='Cache expiration time')

class ReferrerTrackingSerializer(serializers.Serializer):
    """Сериализатор для сохранения данных referrer tracking"""
    referrer = serializers.CharField(allow_blank=True, required=False, allow_null=True)
    landing_url = serializers.CharField(allow_blank=True, required=False, allow_null=True)
    landingUrl = serializers.CharField(allow_blank=True, required=False, allow_null=True, write_only=True)  # Поддержка camelCase
    timestamp = serializers.IntegerField(required=False)
    user_agent = serializers.CharField(required=False, allow_blank=True)
    userAgent = serializers.CharField(required=False, allow_blank=True, write_only=True)  # Поддержка camelCase
    device_type = serializers.CharField(allow_blank=True, required=False)
    deviceType = serializers.CharField(allow_blank=True, required=False, write_only=True)  # Поддержка camelCase
    os_name = serializers.CharField(allow_blank=True, required=False)
    osName = serializers.CharField(allow_blank=True, required=False, write_only=True)  # Поддержка camelCase
    os_version = serializers.CharField(allow_blank=True, required=False)
    osVersion = serializers.CharField(allow_blank=True, required=False, write_only=True)  # Поддержка camelCase
    
    def validate_timestamp(self, value):
        """Конвертируем timestamp в datetime"""
        if value is None:
            return None
        try:
            from datetime import datetime
            return datetime.fromtimestamp(value / 1000)  # Конвертируем из миллисекунд
        except (ValueError, TypeError):
            raise serializers.ValidationError("Invalid timestamp format")
    
    def validate(self, data):
        """Дополнительная валидация данных и нормализация полей"""
        # Нормализуем camelCase в snake_case
        landing_url = data.get('landing_url') or data.get('landingUrl')
        user_agent = data.get('user_agent') or data.get('userAgent')
        device_type = data.get('device_type') or data.get('deviceType')
        os_name = data.get('os_name') or data.get('osName')
        os_version = data.get('os_version') or data.get('osVersion')
        
        # Удаляем camelCase поля, оставляем только snake_case
        data.pop('landingUrl', None)
        data.pop('userAgent', None)
        data.pop('deviceType', None)
        data.pop('osName', None)
        data.pop('osVersion', None)
        
        # Обновляем данные нормализованными значениями
        if landing_url is not None:
            data['landing_url'] = landing_url
        if user_agent is not None:
            data['user_agent'] = user_agent
        if device_type is not None:
            data['device_type'] = device_type
        if os_name is not None:
            data['os_name'] = os_name
        if os_version is not None:
            data['os_version'] = os_version
        
        # Проверяем landing_url (обязательное поле при сохранении)
        if not data.get('landing_url'):
            raise serializers.ValidationError("Landing URL is required")
        
        return data
