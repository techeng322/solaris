"""
Translation system for bilingual (English/Russian) UI support.
"""

class Translations:
    """Bilingual translations for UI elements."""
    
    # Window title
    WINDOW_TITLE = "Solaris - Insolation & KEO Calculator / Расчет инсоляции и КЕО"
    
    # File selection
    FILE_NOT_SELECTED = "File not selected / Файл не выбран"
    SELECT_MODEL = "Select Model (IFC/RVT/GLB) / Выбрать модель (IFC/RVT/GLB)"
    MODEL = "Model / Модель"
    
    # Calculation parameters
    CALCULATION_PARAMETERS = "Calculation Parameters / Параметры расчета"
    CALCULATION_DATE = "Calculation Date / Дата расчета"
    CALCULATION_TYPE = "Calculation Type / Тип расчета"
    CALCULATE = "Calculate / Рассчитать"
    
    # Calculation types
    BOTH = "Insolation & KEO / Инсоляция и КЕО"
    INSOLATION_ONLY = "Insolation Only / Только инсоляция"
    KEO_ONLY = "KEO Only / Только КЕО"
    
    # Status messages
    READY = "Ready / Готов к работе"
    LOADING_MODEL = "Loading model... / Загрузка модели..."
    MODEL_LOADED = "Model loaded / Модель загружена"
    ROOMS_COUNT = "Rooms / Помещений"
    CALCULATING = "Calculating... / Выполняется расчет..."
    CALCULATION_COMPLETE = "Calculation complete / Расчет завершен"
    CALCULATION_ERROR = "Calculation error / Ошибка расчета"
    
    # Table headers
    WINDOW = "Window / Окно"
    INSOLATION = "Insolation / Инсоляция"
    COMPLIANCE = "Compliance / Соответствие"
    KEO_PERCENT = "KEO (%) / КЕО (%)"
    STATUS = "Status / Статус"
    
    # Tabs
    RESULTS = "Results / Результаты"
    LOG = "Log / Лог"
    
    # Buttons
    EXPORT_REPORT = "Export Report / Экспорт отчета"
    SHOW_3D_VIEWER = "Show 3D Viewer / Показать 3D просмотр"
    SHOW_LOGS_VIEWER = "Show Logs Viewer / Показать просмотр логов"
    SHOW_OBJECT_TREE = "Show Object Tree / Показать дерево объектов"
    
    # Menu items
    FILE_MENU = "File / Файл"
    OPEN_MODEL = "Open Model... / Открыть модель..."
    EXIT = "Exit / Выход"
    VIEW_MENU = "View / Вид"
    VIEW_3D = "3D Viewer / 3D просмотр"
    VIEW_LOGS = "Logs Viewer / Просмотр логов"
    VIEW_OBJECT_TREE = "Object Tree / Дерево объектов"
    TOGGLE_FULLSCREEN = "Toggle Fullscreen (F11) / Переключить полноэкранный режим (F11)"
    HELP_MENU = "Help / Справка"
    ABOUT = "About / О программе"
    
    # Messages
    ERROR = "Error / Ошибка"
    WARNING = "Warning / Предупреждение"
    SUCCESS = "Success / Успех"
    NO_BUILDINGS = "Model contains no buildings / Модель не содержит зданий"
    FAILED_TO_LOAD = "Failed to load model / Не удалось загрузить модель"
    LOAD_MODEL_FIRST = "Please load a model first / Сначала загрузите модель"
    NO_RESULTS = "No results to export / Нет результатов для экспорта"
    REPORT_SAVED = "Report saved / Отчет сохранен"
    FAILED_TO_SAVE = "Failed to save report / Не удалось сохранить отчет"
    
    # Calculation summary
    CALCULATION_COMPLETE_MSG = "Calculation complete / Расчет завершен"
    TOTAL_ROOMS = "Total rooms / Всего помещений"
    COMPLIANT_ROOMS = "Compliant rooms / Соответствующих"
    NON_COMPLIANT_ROOMS = "Non-compliant rooms / Не соответствующих"
    COMPLIANCE_RATE = "Compliance rate / Процент соответствия"
    
    # Table values
    YES = "Yes / Да"
    NO = "No / Нет"
    COMPLIANT = "Compliant / Соответствует"
    NON_COMPLIANT = "Non-compliant / Не соответствует"
    N_A = "N/A"
    
    # About dialog
    ABOUT_TITLE = "About / О программе"
    ABOUT_TEXT = """Solaris Insolation Calculator

Program for calculating insolation and KEO
Соответствует ГОСТ Р 57795-2017, СП 52.13330.2016, СП 367.1325800.2017

Version 1.0"""

