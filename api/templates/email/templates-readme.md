    """
    View для предварительного просмотра email шаблонов.
    
    Доступные шаблоны:
    1. task_completed - Уведомление о полном выполнении задания пользователя
    2. daily_tasks - Список доступных заданий на текущий день
    3. complete_registration - Напоминание о незавершенной регистрации
    4. weekly_digest - Еженедельный дайджест со статистикой пользователя
    
    Использование:
    /api/preview-email/?template=task_completed - просмотр шаблона уведомления о выполнении
    /api/preview-email/?template=daily_tasks - просмотр шаблона ежедневных заданий
    /api/preview-email/?template=complete_registration - просмотр шаблона напоминания о регистрации
    /api/preview-email/?template=weekly_digest - просмотр шаблона еженедельного дайджеста
    """