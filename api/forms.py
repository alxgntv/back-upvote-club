from django import forms
from django.contrib.auth.models import User
from .models import UserProfile

class UserFilterForm(forms.Form):
    """Форма для фильтрации пользователей по различным критериям"""
    
    # Основные поля пользователя
    username_contains = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Содержит в username'}),
        label='Username содержит'
    )
    
    # Статус пользователя
    status = forms.MultipleChoiceField(
        choices=UserProfile._meta.get_field('status').choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Статус пользователя'
    )
    
    # Верификация Twitter
    twitter_verification_status = forms.MultipleChoiceField(
        choices=UserProfile._meta.get_field('twitter_verification_status').choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Статус верификации Twitter'
    )
    
    # Поля страны
    has_country_code = forms.ChoiceField(
        choices=[
            ('', 'Любое'),
            ('yes', 'Есть country_code'),
            ('no', 'Нет country_code')
        ],
        required=False,
        label='Наличие country_code'
    )
    
    has_chosen_country = forms.ChoiceField(
        choices=[
            ('', 'Любое'),
            ('yes', 'Есть chosen_country'),
            ('no', 'Нет chosen_country')
        ],
        required=False,
        label='Наличие chosen_country'
    )
    
    # Twitter аккаунт
    has_twitter_account = forms.ChoiceField(
        choices=[
            ('', 'Любое'),
            ('yes', 'Есть Twitter аккаунт'),
            ('no', 'Нет Twitter аккаунта')
        ],
        required=False,
        label='Наличие Twitter аккаунта'
    )
    
    twitter_account_contains = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Содержит в Twitter аккаунте'}),
        label='Twitter аккаунт содержит'
    )
    
    # Баланс
    balance_min = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'placeholder': 'Минимальный баланс'}),
        label='Минимальный баланс'
    )
    
    balance_max = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'placeholder': 'Максимальный баланс'}),
        label='Максимальный баланс'
    )
    
    # Выполненные задания
    has_completed_tasks = forms.ChoiceField(
        choices=[
            ('', 'Любое'),
            ('yes', 'Есть выполненные задания'),
            ('no', 'Нет выполненных заданий')
        ],
        required=False,
        label='Наличие выполненных заданий'
    )
    
    completed_tasks_min = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'placeholder': 'Минимум заданий'}),
        label='Минимум выполненных заданий'
    )
    
    completed_tasks_max = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'placeholder': 'Максимум заданий'}),
        label='Максимум выполненных заданий'
    )
    
    # Доступные задания
    available_tasks_min = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'placeholder': 'Минимум доступных'}),
        label='Минимум доступных заданий'
    )
    
    available_tasks_max = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'placeholder': 'Максимум доступных'}),
        label='Максимум доступных заданий'
    )
    
    # Дата регистрации
    date_joined_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Зарегистрирован с'
    )
    
    date_joined_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Зарегистрирован до'
    )
    
    # Инвайт коды
    has_invite_code = forms.ChoiceField(
        choices=[
            ('', 'Любое'),
            ('yes', 'Использовал инвайт код'),
            ('no', 'Не использовал инвайт код')
        ],
        required=False,
        label='Использование инвайт кода'
    )
    
    # Пробный период
    has_trial = forms.ChoiceField(
        choices=[
            ('', 'Любое'),
            ('yes', 'Есть дата начала триала'),
            ('no', 'Нет даты начала триала')
        ],
        required=False,
        label='Пробный период'
    )
    
    # Амбассадор
    is_ambassador = forms.ChoiceField(
        choices=[
            ('', 'Любое'),
            ('yes', 'Амбассадор'),
            ('no', 'Не амбассадор')
        ],
        required=False,
        label='Статус амбассадора'
    )
    
    # Партнер
    is_affiliate_partner = forms.ChoiceField(
        choices=[
            ('', 'Любое'),
            ('yes', 'Партнер'),
            ('no', 'Не партнер')
        ],
        required=False,
        label='Партнерский статус'
    )
    
    # Расширение Chrome
    chrome_extension_status = forms.ChoiceField(
        choices=[
            ('', 'Любое'),
            ('yes', 'Установлено расширение'),
            ('no', 'Не установлено расширение')
        ],
        required=False,
        label='Статус Chrome расширения'
    )
    
    # PayPal и USDT адреса
    has_paypal_address = forms.ChoiceField(
        choices=[
            ('', 'Любое'),
            ('yes', 'Есть PayPal адрес'),
            ('no', 'Нет PayPal адреса')
        ],
        required=False,
        label='Наличие PayPal адреса'
    )
    
    has_usdt_address = forms.ChoiceField(
        choices=[
            ('', 'Любое'),
            ('yes', 'Есть USDT адрес'),
            ('no', 'Нет USDT адреса')
        ],
        required=False,
        label='Наличие USDT адреса'
    )
    
    # Включить email из Firebase
    include_firebase_email = forms.BooleanField(
        required=False,
        initial=True,
        label='Включить email из Firebase',
        help_text='Получать email адреса из Firebase. Отображается в таблице и CSV.'
    )
    
    # Лимит результатов
    limit_results = forms.IntegerField(
        required=False,
        initial=1000,
        widget=forms.NumberInput(attrs={'placeholder': '1000'}),
        label='Лимит результатов',
        help_text='Максимальное количество результатов (для производительности)'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Добавляем CSS классы для красивого отображения
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs.update({'class': 'checkbox-group'})
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({'class': 'form-control'})
            elif isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.DateInput)):
                field.widget.attrs.update({'class': 'form-control'}) 