import os
import sys
import subprocess
import threading
import time
import json
import webbrowser
import hashlib
import asyncio
import re
import random
import difflib
import datetime
import queue
import logging
from pathlib import Path
from datetime import datetime as dt
import importlib.util

# --- CONFIG & PATHS ---
if getattr(sys, 'frozen', False):
    # PyInstaller environment
    BUNDLE_BASE = Path(sys._MEIPASS).resolve()
    EXE_BASE = Path(sys.executable).resolve().parent
else:
    # Normal Python environment
    BUNDLE_BASE = Path(__file__).resolve().parent
    EXE_BASE = BUNDLE_BASE

WEB_DIR = BUNDLE_BASE / "web"
SOUNDS_DIR = EXE_BASE / "jarvis_sounds"
SOUNDS_DIR.mkdir(exist_ok=True)
CACHE_DIR = SOUNDS_DIR / "tts_cache"
CACHE_DIR.mkdir(exist_ok=True)
CUSTOM_SOUNDS_DIR = EXE_BASE / "звуки"
VOSK_MODEL_DIR = Path(os.environ.get("LOCALAPPDATA", "C:\\")) / "jarvis_vosk" / "vosk-model"
SCENES_PATH = EXE_BASE / "jarvis_scenes.json"
MEMORY_PATH = EXE_BASE / "jarvis_memory.json"
SETTINGS_PATH = EXE_BASE / "jarvis_settings.json"


def download_and_install_sox():
    """Автоматически скачивает и устанавливает SoX на Windows."""
    import platform
    import urllib.request
    import zipfile
    import shutil
    
    if platform.system().lower() != 'windows':
        print("[SOX] Автоматическая установка SoX поддерживается только на Windows.")
        return False
    
    print("[SOX] Начинаю автоматическую установку SoX...")
    
    try:
        # URL для скачивания SoX для Windows (архив)
        # Используем популярный зеркальный URL
        sox_url = "https://sourceforge.net/projects/sox/files/sox/14.4.2/sox-14.4.2-win32.zip/download"
        
        zip_path = EXE_BASE / "sox.zip"

        _last_pct = [-1]
        def _sox_progress(block_num, block_size, total_size):
            if total_size > 0:
                pct = min(int(block_num * block_size * 100 / total_size), 100)
                if pct != _last_pct[0] and pct % 10 == 0:
                    _last_pct[0] = pct
                    print(f"[SOX] Скачивание: {pct}%")

        print("[SOX] Скачиваю SoX...")
        urllib.request.urlretrieve(sox_url, zip_path, reporthook=_sox_progress)
        print("[SOX] Скачивание завершено: 100%")
        
        print("[SOX] Распаковываю архив...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(EXE_BASE / "sox_temp")
        
        # Найти папку с SoX внутри распакованного архива
        sox_extracted_dir = None
        for item in (EXE_BASE / "sox_temp").iterdir():
            if item.is_dir() and "sox" in item.name.lower():
                sox_extracted_dir = item
                break
        
        if sox_extracted_dir is None:
            print("[SOX] Ошибка: не удалось найти папку SoX в архиве")
            return False
        
        # Переместить файлы SoX в корень проекта или в специальную папку
        sox_target_dir = EXE_BASE / "sox"
        if sox_target_dir.exists():
            shutil.rmtree(sox_target_dir)
        
        shutil.move(str(sox_extracted_dir), str(sox_target_dir))
        
        # Добавить путь к SoX в PATH на время выполнения
        sox_bin_path = str(sox_target_dir.resolve())
        os.environ["PATH"] = sox_bin_path + os.pathsep + os.environ["PATH"]
        
        # Попробовать добавить в системный PATH (требует администраторских прав)
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment', 0, winreg.KEY_ALL_ACCESS)
            old_path, _ = winreg.QueryValueEx(key, 'PATH')
            
            if sox_bin_path not in old_path:
                new_path = old_path + os.pathsep + sox_bin_path
                winreg.SetValueEx(key, 'PATH', 0, winreg.REG_EXPAND_SZ, new_path)
                
            winreg.CloseKey(key)
            print("[SOX] SoX добавлен в системный PATH")
        except Exception as e:
            print(f"[SOX] Не удалось добавить SoX в системный PATH (нужны права администратора): {e}")
            print(f"[SOX] Временно добавлен в PATH процесса: {sox_bin_path}")
        
        # Удалить временные файлы
        if zip_path.exists():
            zip_path.unlink()
        if (EXE_BASE / "sox_temp").exists():
            shutil.rmtree(EXE_BASE / "sox_temp")
        
        print("[SOX] SoX успешно установлен!")
        return True
        
    except Exception as e:
        print(f"[SOX] Ошибка при установке SoX: {e}")
        return False


def download_and_install_vosk_model():
    """Автоматически скачивает и устанавливает русскоязычную модель Vosk."""
    import urllib.request
    import tarfile
    import shutil

    print("[VOSK] Начинаю автоматическую установку русской модели Vosk...")

    try:
        # URL для скачивания русской модели Vosk (проверенная рабочая версия)
        vosk_model_url = "https://alphacephei.com/vosk/models/vosk-model-ru-0.22.zip"

        # Используем ASCII-безопасные пути (Vosk не поддерживает кириллицу в путях)
        vosk_base = VOSK_MODEL_DIR.parent
        vosk_base.mkdir(parents=True, exist_ok=True)
        model_zip_path = vosk_base / "vosk-model-ru.zip"
        temp_dir = vosk_base / "vosk_temp"

        # Скачивание с отображением прогресса в процентах
        _last_pct = [-1]
        def _progress_hook(block_num, block_size, total_size):
            if total_size > 0:
                pct = int(block_num * block_size * 100 / total_size)
                pct = min(pct, 100)
                if pct != _last_pct[0] and pct % 5 == 0:
                    _last_pct[0] = pct
                    size_mb = total_size / (1024 * 1024)
                    done_mb = min(block_num * block_size, total_size) / (1024 * 1024)
                    print(f"[VOSK] Скачивание модели: {pct}% ({done_mb:.0f}/{size_mb:.0f} МБ)")

        print("[VOSK] Скачиваю русскую модель Vosk...")
        urllib.request.urlretrieve(vosk_model_url, model_zip_path, reporthook=_progress_hook)
        print("[VOSK] Скачивание завершено: 100%")

        print("[VOSK] Распаковываю модель...")
        import zipfile
        with zipfile.ZipFile(model_zip_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            print(f"[VOSK] Файлы в архиве: {file_list[:10]}...")
            zip_ref.extractall(temp_dir)

        # Проверим, что в временной папке есть подпапки
        temp_contents = list(temp_dir.iterdir())
        print(f"[VOSK] Содержимое временной папки: {[item.name for item in temp_contents]}")

        # Найти папку с моделью внутри распакованного архива
        extracted_model_dir = None
        for item in temp_contents:
            if item.is_dir():
                extracted_model_dir = item
                break

        if extracted_model_dir is None:
            print("[VOSK] Ошибка: не удалось найти папку модели в архиве")
            return False

        print(f"[VOSK] Найдена папка модели: {extracted_model_dir.name}")

        # Удалить существующую модель, если есть
        if VOSK_MODEL_DIR.exists():
            shutil.rmtree(VOSK_MODEL_DIR)

        # Переместить модель в целевую папку
        shutil.move(str(extracted_model_dir), str(VOSK_MODEL_DIR))

        # Убедимся, что структура файлов правильная
        required_subdirs = ['am', 'conf', 'graph', 'ivector']
        for subdir in required_subdirs:
            subdir_path = VOSK_MODEL_DIR / subdir
            if not subdir_path.exists():
                print(f"[VOSK] Ошибка: отсутствует подкаталог {subdir} в модели")
                return False

        # Проверим наличие ключевых файлов
        required_files = [
            'am/final.mdl',
            'conf/mfcc.conf',
            'conf/model.conf'
        ]

        for file_path in required_files:
            full_path = VOSK_MODEL_DIR / file_path
            if not full_path.exists():
                print(f"[VOSK] Ошибка: отсутствует файл {file_path} в модели")
                return False

        print(f"[VOSK] Структура модели проверена, все необходимые файлы присутствуют")
        print(f"[VOSK] Модель установлена в: {VOSK_MODEL_DIR}")

        # Удалить временные файлы
        if model_zip_path.exists():
            model_zip_path.unlink()
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

        print("[VOSK] Русская модель Vosk успешно установлена!")
        return True
        
    except Exception as e:
        print(f"[VOSK] Ошибка при установке модели Vosk: {e}")
        return False


def check_and_install_sox():
    """Проверяет наличие SoX в системе и при необходимости устанавливает его."""
    try:
        result = subprocess.run(['sox', '--version'], capture_output=True, text=True, creationflags=0x08000000 if os.name == 'nt' else 0)
        if result.returncode == 0:
            print("[SOX] SoX уже установлен и доступен в системе")
            return True
    except FileNotFoundError:
        pass
    
    print("[SOX] SoX не найден в системе. Пытаюсь выполнить автоматическую установку...")
    
    success = download_and_install_sox()
    if success:
        # Проверим снова после установки
        try:
            result = subprocess.run(['sox', '--version'], capture_output=True, text=True, creationflags=0x08000000 if os.name == 'nt' else 0)
            if result.returncode == 0:
                print("[SOX] SoX успешно установлен и готов к использованию")
                return True
        except FileNotFoundError:
            pass
    
    print("[SOX] Не удалось установить SoX автоматически")
    return False


def check_and_update_vosk_model():
    """Проверяет и при необходимости устанавливает/обновляет модель Vosk."""
    import shutil

    model_path = VOSK_MODEL_DIR
    model_path.parent.mkdir(parents=True, exist_ok=True)
    required_files = ['am/final.mdl', 'conf/mfcc.conf', 'conf/model.conf']

    # Миграция: перенести модель из старого кириллического пути, если она там есть
    old_model = EXE_BASE / "vosk-model"
    if old_model.exists() and not model_path.exists():
        print("[VOSK] Перемещаю модель из старого пути в ASCII-безопасный...")
        try:
            shutil.move(str(old_model), str(model_path))
            print(f"[VOSK] Модель перемещена в: {model_path}")
        except Exception as e:
            print(f"[VOSK] Не удалось переместить модель: {e}")
    # Удалить старую папку если она осталась после миграции
    if old_model.exists():
        try:
            shutil.rmtree(old_model)
        except Exception:
            pass
    
    # Проверяем, существует ли папка модели и содержит ли она необходимые файлы
    if model_path.exists():
        missing_files = []
        for req_file in required_files:
            if not (model_path / req_file).exists():
                missing_files.append(req_file)
        
        if not missing_files:
            # Проверим, действительно ли модель работает
            try:
                from vosk import Model
                test_model = Model(str(model_path))
                print("[VOSK] Модель Vosk уже установлена и работает корректно")
                # Сбрасываем счетчик неудачных попыток и включаем Vosk
                reset_vosk_failure_count()
                return True
            except Exception as e:
                print(f"[VOSK] Существующая модель Vosk не работает: {e}")
        else:
            print(f"[VOSK] Модель Vosk неполная, отсутствуют файлы: {missing_files}")
    else:
        print("[VOSK] Модель Vosk не найдена")
    
    print("[VOSK] Пытаюсь установить русскую модель Vosk...")
    success = download_and_install_vosk_model()
    if success:
        # Проверим, работает ли новая модель
        try:
            from vosk import Model
            test_model = Model(str(model_path))
            print("[VOSK] Новая модель Vosk успешно установлена и работает")
            # Сбрасываем счетчик неудачных попыток и включаем Vosk
            reset_vosk_failure_count()
            return True
        except Exception as e:
            print(f"[VOSK] Установленная модель Vosk не работает: {e}")
            # Попробуем альтернативный подход - может быть проблема с кэшем или временными файлами
            import os
            import shutil
            try:
                # Удалим и заново создадим папку модели
                shutil.rmtree(model_path)
                # Повторно установим модель
                success_retry = download_and_install_vosk_model()
                if success_retry:
                    test_model = Model(str(model_path))
                    print("[VOSK] Модель Vosk успешно установлена после повторной установки")
                    reset_vosk_failure_count()
                    return True
            except Exception as retry_error:
                print(f"[VOSK] Повторная установка модели также не удалась: {retry_error}")
            return False
    
    print("[VOSK] Не удалось установить модель Vosk автоматически")
    return False


def reset_vosk_failure_count():
    """Сбрасывает счетчик неудачных попыток Vosk, когда модель успешно установлена."""
    global jarvis
    try:
        if jarvis:
            jarvis.vosk_failed_attempts = 0
            # Включаем Vosk в настройках, если он был отключен
            if not jarvis.settings.get("use_vosk", False):
                jarvis.settings["use_vosk"] = True
                jarvis.save_json(EXE_BASE / "jarvis_settings.json", jarvis.settings)
                print("[VOSK] Vosk снова включен после успешной установки модели")
    except Exception:
        pass

class SmartHomeController:
    def __init__(self, jarvis_instance):
        self.jarvis = jarvis_instance
        self.devices = {}
        self.api_url = None
        self.access_token = None
        
    def initialize(self, config):
        """Инициализация контроллера умного дома"""
        self.api_url = config.get("api_url")
        self.access_token = config.get("access_token")
        self.jarvis.log("Контроллер умного дома инициализирован")
        
    def register_device(self, device_id, device_type, name, room=None):
        """Регистрация нового устройства"""
        self.devices[device_id] = {
            "type": device_type,
            "name": name,
            "room": room,
            "state": "unknown"
        }
        
    def get_devices_by_room(self, room):
        """Получить список устройств в комнате"""
        return {id: dev for id, dev in self.devices.items() if dev.get("room") == room}
        
    def get_devices_by_type(self, device_type):
        """Получить список устройств по типу"""
        return {id: dev for id, dev in self.devices.items() if dev.get("type") == device_type}
        
    def turn_on(self, device_id):
        """Включить устройство"""
        if device_id in self.devices:
            # Здесь будет вызов API для включения устройства
            self.jarvis.log(f"Включаю устройство {self.devices[device_id]['name']}")
            self.devices[device_id]["state"] = "on"
            return True
        return False
        
    def turn_off(self, device_id):
        """Выключить устройство"""
        if device_id in self.devices:
            # Здесь будет вызов API для выключения устройства
            self.jarvis.log(f"Выключаю устройство {self.devices[device_id]['name']}")
            self.devices[device_id]["state"] = "off"
            return True
        return False
        
    def toggle(self, device_id):
        """Переключить состояние устройства"""
        if device_id in self.devices:
            current_state = self.devices[device_id]["state"]
            if current_state == "on":
                return self.turn_off(device_id)
            else:
                return self.turn_on(device_id)
        return False

class PluginManager:
    def __init__(self, jarvis_instance):
        self.jarvis = jarvis_instance
        self.plugins = {}
        self.plugin_dir = EXE_BASE / "plugins"
        self.plugin_dir.mkdir(exist_ok=True)
    
    def load_plugin(self, plugin_name):
        """Загрузка плагина по имени"""
        plugin_path = self.plugin_dir / f"{plugin_name}.py"
        if not plugin_path.exists():
            self.jarvis.log(f"Плагин {plugin_name} не найден")
            return False
            
        try:
            spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Проверяем, есть ли в плагине необходимые функции
            if hasattr(module, 'initialize'):
                module.initialize(self.jarvis)
                self.plugins[plugin_name] = module
                self.jarvis.log(f"Плагин {plugin_name} загружен")
                return True
        except Exception as e:
            self.jarvis.log(f"Ошибка загрузки плагина {plugin_name}: {e}")
            return False
    
    def load_all_plugins(self):
        """Загрузка всех плагинов из директории"""
        for plugin_file in self.plugin_dir.glob("*.py"):
            plugin_name = plugin_file.stem
            if plugin_name != "__init__":
                self.load_plugin(plugin_name)

class Localization:
    def __init__(self, lang_code="ru"):
        self.lang_code = lang_code
        self.translations = {}

    def set_language(self, lang_code):
        self.lang_code = lang_code

    def get(self, key, lang_code=None):
        # Возвращаем ключ как есть, без перевода
        return key

class JarvisLogger:
    def __init__(self, log_file_path):
        self.log_file = log_file_path
        self.logger = logging.getLogger('jarvis')
        self.logger.setLevel(logging.DEBUG)
        
        # Создаем форматтер
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        # Файловый хэндлер
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        
        # Консольный хэндлер
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def info(self, message):
        self.logger.info(message)
    
    def warning(self, message):
        self.logger.warning(message)
    
    def error(self, message):
        self.logger.error(message)
    
    def debug(self, message):
        self.logger.debug(message)

# --- AUTO-INSTALLER ---
def install_dependencies():
    required = [
        "eel", "psutil",
        "speech_recognition", "pyautogui",
        "pyperclip", "keyboard", "pygame", "opencv-python",
        "pytesseract", "llama-cpp-python", "hf_transfer", "huggingface_hub",
        "vosk", "edge-tts"
    ]
    for lib in required:
        try:
            mod_name = lib.replace("-", "_")
            if lib == "opencv-python": mod_name = "cv2"
            if lib == "llama-cpp-python": mod_name = "llama_cpp"
            __import__(mod_name)
        except ImportError:
            print(f"[INIT] Установка {lib}...")
            flags = 0x08000000 if os.name == 'nt' else 0
            proc = subprocess.Popen(
                [sys.executable, "-m", "pip", "install", lib],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, creationflags=flags
            )
            for line in proc.stdout:
                line = line.strip()
                if line and ("Downloading" in line or "Installing" in line or "%" in line):
                    print(f"[INIT] {lib}: {line}")
            proc.wait()
            if proc.returncode != 0:
                print(f"[INIT] Ошибка установки {lib}")
            else:
                print(f"[INIT] {lib} установлен успешно")

    # Проверяем SoX отдельно, так как это системная утилита, а не Python-библиотека
    check_and_install_sox()

    # Модель Vosk будет проверяться и устанавливаться при инициализации JarvisEel,
    # в зависимости от настроек пользователя

print("[START] Checking dependencies...")
install_dependencies()

import eel
# pyttsx3 отключён — вызывает access violation (COM/SAPI) в многопоточном окружении
# import pyttsx3
import speech_recognition as sr
import pygame
import pyautogui
import keyboard
import pyperclip
try:
    import cv2
    import pytesseract
    OCR_AVAILABLE = True
except:
    OCR_AVAILABLE = False

# Movie Phrases Mapping
MOVIE_PHRASES = {
    "привет": "hello_stark.mp3",
    "джарвис": "yes_sir.mp3",
    "какие планы": "schemes.mp3",
    "запуск": "startup_sequence.mp3",
    "готов": "ready_to_serve.mp3"
}

# Частые фразы — прогреваются в кэш после загрузки Qwen TTS
COMMON_TTS_PHRASES = (
    "Слушаю, сэр.",
    "Сэр, не могу ответить.",
    "Сэр, ИИ сейчас отключён. Включите Онлайн или Локальный режим в настройках.",
    "Подтверждено. Выключаюсь.",
    "Отменено.",
    "До встречи, сэр.",
    "Не понял команду.",
    "Обрабатываю запрос.",
    "Голосовые системы синхронизированы.",
    "Смотрю...",
)

# --- JARVIS CORE LOGIC ---
class JarvisEel:
    def __init__(self):
        self.qwen_tts_lock = threading.Lock()
        self.is_listening = True
        self.is_speaking = False
        self.stop_requested = False
        self.dictation_active = False
        self.learning_mode = False  # Режим обучения
        self.temp_command = None  # Временное хранилище для новой команды
        self.power_saving_mode = False  # Режим энергосбережения
        self.low_power_animation = False  # Анимация в режиме энергосбережения
        self.voice_queue = queue.Queue()
        self.last_activity_time = time.time()
        self._warned_once = set()
        self.pending_confirmation = None  # {"kind": "...", "payload": {...}}
        self.chat_memory = []  # [{"role": "user"/"assistant", "content": "..."}]
        self.vosk_failed_attempts = 0  # Счетчик неудачных попыток загрузки Vosk
        self.max_vosk_failures = 3  # Максимальное количество неудачных попыток
        
        # Commands
        self.cmds = self.load_json(EXE_BASE / "jarvis_cmds.json", {
            "открой калькулятор": {"action": "calc.exe", "action_type": "program"}
        })
        self.scenes = self.load_json(SCENES_PATH, {})
        self.chat_memory = self.load_json(MEMORY_PATH, [])
        
        # Models
        self.qwen_llm_model = None
        self.qwen_llm_loading = False
        self.qwen_model = None
        self.qwen_ready = False
        self.qwen_loading = False
        self._qwen_voice_prompt = None
        self._qwen_ref_path = None
        
        # CosyVoice State
        self.cosyvoice_model = None
        self.cosyvoice_ready = False
        self.cosyvoice_loading = False
        self.cosyvoice_lock = threading.Lock()
        self.cosyvoice_api_confirmed = False  # True only after a real successful API response
        
        self.settings = self.load_json(EXE_BASE / "jarvis_settings.json", {
            "use_movie_sounds": True,
            "use_qwen_llm": False,
            "use_qwen_tts": False,
            "qwen_reference_path": "",

            # Local LLM custom model path
            "local_llm_path": "",
            "local_llm_gpu_layers": -1,

            # CosyVoice Settings
            "use_cosyvoice_tts": False,
            "cosyvoice_reference_path": "",
            "cosyvoice_model": "FunAudioLLM/CosyVoice-300M-Instruct",
            "cosyvoice_mode": "local",  # "local" или "api"
            "cosyvoice_api_url": "http://127.0.0.1:9880",
            "cosyvoice_prompt_text": "",

            # STT
            "use_vosk": False,
            "vosk_model_path": "",
            "vosk_min_conf": 0.60,

            # Qwen memory
            "memory_max_turns": 6,

            # Safety
            "confirm_dangerous": True,
            
            
            # Power saving
            "power_saving_enabled": False,
            
            # Performance modes
            "performance_mode": "balanced",  # "eco", "balanced", "performance"
            # TTS speed optimizations
            "tts_single_pass": True,
            "tts_prewarm_cache": True,
            "tts_keep_gpu_warm": True,
        })
        
        # Audio Initialization
        try:
            pygame.mixer.init()
        except Exception as e:
            print(f"[WARN] pygame mixer init failed: {e}")
        
        # pyttsx3 отключён — вызывает access violation на Windows
        # Используем только Edge TTS (облачный, высокое качество)
        self.engine = None
        
        # Инициализируем улучшенное логирование
        self.logger = JarvisLogger(EXE_BASE / "jarvis_detailed.log")
        
        # Инициализируем локализацию
        self.localization = Localization()

        # Recognition Initialization
        self.recognizer = sr.Recognizer()
        try:
            self.mic = sr.Microphone()
        except Exception as e:
            self.log(f"⚠ Ошибка инициализации микрофона: {e}")
            self.mic = None
        
        # Start Workers (Internal)
        threading.Thread(target=self._speech_worker, daemon=True).start()
        threading.Thread(target=self._listen_loop, daemon=True).start()
        threading.Thread(target=self._deep_sleep_monitor, daemon=True).start()
        # Визуализатор запускается с задержкой, чтобы не конфликтовать с микрофоном
        threading.Thread(target=self._audio_visualizer, daemon=True).start()
        # Запускаем мониторинг режима энергосбережения
        threading.Thread(target=self._power_saving_monitor, daemon=True).start()

        # Проверяем и устанавливаем модель Vosk, если она включена в настройках
        if self.settings.get("use_vosk", False):
            check_and_update_vosk_model()
        
        # Инициализируем менеджер плагинов и загружаем все плагины
        self.plugin_manager = PluginManager(self)
        self.plugin_manager.load_all_plugins()
        
        # Инициализируем контроллер умного дома
        self.smart_home = SmartHomeController(self)
        # Загружаем конфигурацию умного дома из настроек
        smart_home_config = {
            "api_url": self.settings.get("smart_home_api_url", ""),
            "access_token": self.settings.get("smart_home_access_token", "")
        }
        self.smart_home.initialize(smart_home_config)

    def _audio_visualizer(self):
        """Визуализатор без PyAudio — безопасная пульсация ядра HUD.
        PyAudio конфликтует с speech_recognition при одновременном доступе к микрофону,
        вызывая access violation на Windows. Используем анимированную пульсацию."""
        time.sleep(3)

        # Play startup sound if movie sounds are on
        if self.settings.get("use_movie_sounds"):
            threading.Thread(target=self._play_sync, args=(SOUNDS_DIR / "power_up.mp3",), daemon=True).start()

        self.log("🎤 Визуализатор HUD запущен.")

        import math
        t = 0.0
        while True:
            try:
                # Отправляем состояние в UI
                status_info = {
                    "is_speaking": self.is_speaking,
                    "is_listening": self.is_listening,
                    "is_learning": self.learning_mode,
                    "is_power_saving": self.power_saving_mode,
                    "energy": 0.0
                }
                
                if self.power_saving_mode:
                    # Уменьшенная анимация в режиме энергосбережения
                    energy = 0.02 + 0.01 * math.sin(t * 0.5)
                    status_info["energy"] = energy
                    status_info["state"] = "power_saving"
                    eel.set_status(status_info)()
                elif self.is_speaking:
                    # Активная анимация при разговоре
                    energy = 0.5 + 0.5 * math.sin(t * 8)
                    status_info["energy"] = energy
                    status_info["state"] = "speaking"
                    eel.set_status(status_info)()
                elif self.is_listening:
                    # Анимация при прослушивании
                    energy = 0.1 + 0.15 * math.sin(t * 2)
                    status_info["energy"] = energy
                    status_info["state"] = "listening"
                    eel.set_status(status_info)()
                elif self.learning_mode:
                    # Особая анимация в режиме обучения
                    energy = 0.3 + 0.2 * math.sin(t * 5)
                    status_info["energy"] = energy
                    status_info["state"] = "learning"
                    eel.set_status(status_info)()
                else:
                    # Состояние ожидания
                    status_info["energy"] = 0.05
                    status_info["state"] = "idle"
                    eel.set_status(status_info)()
                    
            except Exception:
                pass
            t += 0.05
            time.sleep(0.05)

    def load_json(self, path, default):
        if path.exists():
            try:
                with open(path, "r", encoding='utf-8') as f: return json.load(f)
            except: return default
        return default

    def save_json(self, path, data):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            self._log_once(f"save_json:{path}", f"⚠ Ошибка сохранения {path.name}: {e}")
            return False

    def log(self, text):
        try:
            timestamp = dt.now().strftime("[%Y-%m-%d %H:%M:%S]")
            log_msg = f"{timestamp} [JARVIS] {text}"
            print(log_msg)
            self.logger.info(text)
        except UnicodeEncodeError:
            # Консоль cp1251 не поддерживает эмодзи — выводим без них
            safe = text.encode('ascii', 'replace').decode('ascii')
            print(f"[JARVIS] {safe}")
        try:
            eel.add_log(text)()
        except Exception as e:
            # UI может быть не готово в первые секунды
            self._log_once("eel_add_log", f"⚠ UI не принял лог: {e}")

    def log_exception(self, context="General"):
        """Логирование исключений с трассировкой"""
        import traceback
        exc_str = traceback.format_exc()
        self.logger.error(f"Exception in {context}: {exc_str}")

    def _power_saving_monitor(self):
        """Мониторинг бездействия для режима энергосбережения"""
        while True:
            # Проверяем, включена ли функция энергосбережения в настройках
            if self.settings.get("power_saving_enabled", False):
                idle_time = time.time() - self.last_activity_time
                
                # Если бездействие больше 10 минут, переходим в режим энергосбережения
                if idle_time > 600:  # 10 минут
                    if not self.power_saving_mode:
                        self.enter_power_saving_mode()
                # Если активность возобновилась и мы в режиме энергосбережения
                elif self.power_saving_mode and idle_time < 30:  # 30 секунд активности
                    self.exit_power_saving_mode()
            else:
                # Если режим энергосбережения отключен в настройках, но активен - выходим из него
                if self.power_saving_mode:
                    self.exit_power_saving_mode()
            
            time.sleep(30)  # Проверяем каждые 30 секунд

    def enter_power_saving_mode(self):
        """Вход в режим энергосбережения"""
        self.power_saving_mode = True
        self.log(self.localization.get("power_saving_on"))
        
        # Уменьшаем частоту опроса
        self.power_save_original_interval = getattr(self, '_listen_interval', 0.5)
        # В реальной реализации можно уменьшить частоту проверок
        
        # Уменьшаем анимацию
        self.low_power_animation = True

    def adjust_performance_mode(self):
        """Настройка параметров в зависимости от режима производительности"""
        mode = self.settings.get("performance_mode", "balanced")
        
        # Отключаем динамическую подстройку — она задирает порог и перестаёт слышать тихую речь
        self.recognizer.dynamic_energy_threshold = False
        
        if mode == "eco":
            self.recognizer.energy_threshold = 150
            self.recognizer.pause_threshold = 2.5
            self.performance_factor = 0.7
        elif mode == "performance":
            self.recognizer.energy_threshold = 50  # Максимальная чувствительность
            self.recognizer.pause_threshold = 1.5
            self.performance_factor = 1.3
        else:  # balanced
            self.recognizer.energy_threshold = 100  # Слышит даже тихую речь
            self.recognizer.pause_threshold = 2.0
            self.performance_factor = 1.0

    def exit_power_saving_mode(self):
        """Выход из режима энергосбережения"""
        if self.power_saving_mode:
            self.power_saving_mode = False
            self.low_power_animation = False
            self.log(self.localization.get("power_saving_off"))
            
            # Восстанавливаем нормальную работу

    def _log_once(self, key: str, text: str):
        """Логирует сообщение только один раз за запуск (чтобы не спамить)."""
        try:
            if key in self._warned_once:
                return
            self._warned_once.add(key)
            self.log(text)
        except Exception:
            pass

    def speak(self, text):
        if not text: return
        self.voice_queue.put(text)

    def _speech_worker(self):
        while True:
            text = self.voice_queue.get()
            self.is_speaking = True
            try: eel.set_speaking(True)()
            except Exception as e:
                self._log_once("eel_set_speaking_true", f"⚠ UI не обновил статус речи: {e}")
            
            # Deep Text cleaning for high-quality TTS
            # 1. Remove Markdown bold/italic
            text = re.sub(r'[*_#]', '', text)
            # 2. Remove text in parentheses (often contains years, etc. that can confuse TTS)
            text = re.sub(r'\([^)]*\)', '', text)
            # 3. Clean up extra dashes and whitespace
            text = text.replace(' — ', '. ').replace(' - ', ' ')
            # 4. Remove any double dots or spaces
            text = re.sub(r'\.\.+', '.', text)
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Movie Sounds Check
            if self.settings.get("use_movie_sounds"):
                clean_text = re.sub(r'[^\w]', '', text.lower())
                found_movie = False
                for key, audio_file in MOVIE_PHRASES.items():
                    if key in clean_text:
                        path = SOUNDS_DIR / audio_file
                        if path.exists():
                            self._play_sync(path)
                            found_movie = True
                            break
                if found_movie:
                    self._end_speech()
                    continue

            self.stop_requested = False
            single_pass = self.settings.get("tts_single_pass", True)

            if single_pass:
                # Потоковый pipeline: разбиваем на предложения и воспроизводим
                # первое сразу, пока остальные генерируются в фоне (как Алиса)
                raw_sentences = re.split(r'(?<=[.!?])\s+', text)
                sentences = []
                for s in raw_sentences:
                    s = s.strip()
                    if s and re.search(r'[a-zA-Zа-яА-ЯёЁ0-9]', s):
                        sentences.append(s)
                
                if not sentences and re.search(r'[a-zA-Zа-яА-ЯёЁ0-9]', text):
                    sentences = [text]
                
                if not sentences:
                    self._end_speech()
                    continue

                # Определяем расширение: Qwen3-TTS пишет в .wav, Edge TTS пишет в .mp3
                # CosyVoice API использует .wav только если сервер реально доступен
                use_qwen = self.settings.get("use_qwen_tts") and self.qwen_ready
                _cosy_local = self.settings.get("use_cosyvoice_tts") and self.cosyvoice_ready and self.cosyvoice_model is not None
                _cosy_api = self.settings.get("use_cosyvoice_tts") and self.settings.get("cosyvoice_mode") == "api" and self.cosyvoice_api_confirmed
                use_cosyvoice = _cosy_local or _cosy_api
                ext = ".wav" if (use_qwen or use_cosyvoice) else ".mp3"

                if len(sentences) == 1:
                    # Одно предложение — без overhead на pipeline
                    path = CACHE_DIR / f"{self._tts_cache_key(sentences[0])}{ext}"
                    if not path.exists():
                        self._generate_tts(sentences[0], path)
                    if path.exists() and not self.stop_requested:
                        self._play_sync(path)
                else:
                    # Несколько предложений — pipeline с опережающей генерацией
                    # maxsize=3: продюсер может уйти вперёд на 3 предложения
                    audio_queue = queue.Queue(maxsize=3)

                    def _producer():
                        for part in sentences:
                            if self.stop_requested:
                                break
                            p = CACHE_DIR / f"{self._tts_cache_key(part)}{ext}"
                            if not p.exists():
                                self._generate_tts(part, p)
                            audio_queue.put(p)
                        audio_queue.put(None)

                    threading.Thread(target=_producer, daemon=True).start()
                    while True:
                        p = audio_queue.get()
                        if p is None or self.stop_requested:
                            break
                        if p.exists():
                            self._play_sync(p)
            else:
                # Режим одного файла: весь текст → один WAV/MP3 → воспроизведение
                use_qwen = self.settings.get("use_qwen_tts") and self.qwen_ready
                _cosy_local = self.settings.get("use_cosyvoice_tts") and self.cosyvoice_ready and self.cosyvoice_model is not None
                _cosy_api = self.settings.get("use_cosyvoice_tts") and self.settings.get("cosyvoice_mode") == "api" and self.cosyvoice_api_confirmed
                use_cosyvoice = _cosy_local or _cosy_api
                ext = ".wav" if (use_qwen or use_cosyvoice) else ".mp3"
                path = CACHE_DIR / f"{self._tts_cache_key(text)}{ext}"
                if not path.exists():
                    self._generate_tts(text, path)
                if path.exists() and not self.stop_requested:
                    self._play_sync(path)

            self._end_speech()
            self.stop_requested = False

    def _tts_cache_key(self, text):
        """Ключ кэша: голос + текст (смена референса сбрасывает кэш)."""
        ref = self.settings.get("cosyvoice_reference_path") or self.settings.get("qwen_reference_path") or ""
        if isinstance(ref, str):
            ref = ref.strip(' \t\n\r"')
        if not ref or not Path(ref).exists():
            ref = str(EXE_BASE / "voice.mp3")
        raw = f"{ref}|{text.strip()}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _warm_tts_cache(self):
        """Фоновый прогрев кэша частых фраз."""
        if not self.settings.get("tts_prewarm_cache", True):
            return
        if not self.qwen_ready:
            return
        warmed = 0
        for phrase in COMMON_TTS_PHRASES:
            if self.stop_requested:
                break
            path = CACHE_DIR / f"{self._tts_cache_key(phrase)}.wav"
            if path.exists():
                continue
            if self._generate_tts(phrase, path):
                warmed += 1
        if warmed:
            self.log(f"💾 Кэш TTS: прогрето {warmed} фраз.")

    def _generate_tts(self, text, path):
        """Генерация TTS через локальный Qwen3-TTS, CosyVoice или облачный Edge TTS."""
        # 1. Qwen3-TTS (High fidelity Voice Clone)
        if self.settings.get("use_qwen_tts") and self.qwen_ready:
            if self._generate_qwen(text, path):
                self.log("🎭 Qwen3-TTS (Клонированный голос)")
                return True

        # 1.5. CosyVoice (High fidelity Voice Clone / API)
        if self.settings.get("use_cosyvoice_tts") and (self.cosyvoice_ready or self.settings.get("cosyvoice_mode") == "api"):
            if self._generate_cosyvoice(text, path):
                self.log("🎭 CosyVoice (Клонированный голос)")
                return True

        # 2. Edge TTS (Высокоскоростной облачный синтез)
        if self.settings.get("use_edge_tts", True):
            if self._generate_edge(text, path):
                self.log("🌐 Edge TTS (Быстрый облачный голос)")
                return True

        # 3. Резервный вариант: создаем пустой файл, чтобы избежать повторных попыток генерации
        # и обеспечить отображение текста в интерфейсе
        try:
            import wave
            import numpy as np
            
            # Создаем короткий тоновый сигнал для пустого аудиофайла
            sample_rate = 22050
            duration = 0.1  # 100ms тишины
            frames = b'\x00' * int(sample_rate * duration * 2)  # 16-bit samples
            
            with wave.open(str(path), 'wb') as wav_file:
                wav_file.setnchannels(1)  # моно
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(frames)
            
            return True
        except Exception as e:
            self.log(f"⚠ Ошибка создания резервного аудиофайла: {e}")
            return False

    def _play_sync(self, path):
        if not path or not Path(path).exists():
            return
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not self.stop_requested:
                time.sleep(0.1)
            if self.stop_requested:
                pygame.mixer.music.stop()
        except Exception as e:
            self._log_once("play_sync", f"⚠ Ошибка воспроизведения звука: {e}")

    def _play_random_custom_sound(self):
        """Воспроизводит случайный звук из папки 'звуки', если она существует."""
        try:
            if not CUSTOM_SOUNDS_DIR.exists():
                return
            files = [p for p in CUSTOM_SOUNDS_DIR.iterdir()
                     if p.is_file() and p.suffix.lower() in (".wav", ".mp3", ".ogg")]
            if not files:
                return
            path = random.choice(files)
            self._play_sync(path)
        except Exception as e:
            self.log(f"Ошибка пользовательского звука: {e}")

    def _end_speech(self):
        self.is_speaking = False
        try: eel.set_speaking(False)()
        except Exception as e:
            self._log_once("eel_set_speaking_false", f"⚠ UI не обновил статус речи: {e}")

    def stop_speech(self):
        """Немедленная остановка речи — очистка очереди, остановка плеера."""
        try:
            self.stop_requested = True
            # Очищаем очередь голоса
            while not self.voice_queue.empty():
                try:
                    self.voice_queue.get_nowait()
                except Exception:
                    break
            # Немедленно останавливаем воспроизведение
            pygame.mixer.music.stop()
            self.is_speaking = False
            self.log("🛑 Речь остановлена")
            try: eel.set_speaking(False)()
            except Exception: pass
        except Exception:
            pass

    def _enter_learning_mode(self):
        """Вход в режим обучения"""
        self.learning_mode = True
        localized_msg = self.localization.get("learning_mode_on") + ". " + self.localization.get("new_phrase")
        self.speak(localized_msg)

    def _process_learning_input(self, text):
        """Обработка ввода в режиме обучения"""
        if not self.temp_command:
            # Сохраняем ключевую фразу
            self.temp_command = {"phrase": text}
            localized_msg = self.localization.get("new_action")
            self.speak(localized_msg)
        else:
            # Сохраняем действие
            self.temp_command["action"] = text
            localized_msg = f"{self.localization.get('command_saved')}: '{self.temp_command['phrase']}' -> '{text}'"
            self.speak(localized_msg)
            
            # Добавляем команду в словарь
            self.cmds[self.temp_command["phrase"]] = {
                "action": self.temp_command["action"],
                "action_type": "text"
            }
            
            # Сохраняем в файл
            self.save_json(EXE_BASE / "jarvis_cmds.json", self.cmds)
            
            # Сброс состояния
            self.temp_command = None
            self.learning_mode = False
            self.speak(self.localization.get("command_saved"))

    def _process_smart_home_command(self, text):
        """Обработка команд умного дома"""
        text_lower = text.lower()
        
        # Проверяем, является ли команда командой умного дома
        smart_home_keywords = ["включи", "выключи", "переключи", "открой", "закрой", "температура"]
        
        # Проверяем наличие ключевых слов умного дома
        if not any(keyword in text_lower for keyword in smart_home_keywords):
            return False
        
        # Примеры команд:
        # "включи свет в гостиной"
        # "выключи музыку в спальне"
        # "установи температуру в кухне на 22 градуса"
        
        # Парсим команду
        device = None
        room = None
        action = None
        
        # Определяем действие
        if "включи" in text_lower or "включить" in text_lower:
            action = "turn_on"
        elif "выключи" in text_lower or "выключить" in text_lower:
            action = "turn_off"
        elif "переключи" in text_lower or "переключить" in text_lower:
            action = "toggle"
        
        # Если действие не определено, выходим
        if not action:
            return False
        
        # Ищем комнату в тексте
        rooms = ["гостиная", "спальня", "кухня", "ванная", "коридор", "офис", "детская"]
        for r in rooms:
            if r in text_lower:
                room = r
                break
        
        # Ищем устройство в тексте
        devices = ["свет", "лампа", "музыка", "колонка", "кондиционер", "обогреватель", "телевизор"]
        for d in devices:
            if d in text_lower:
                device = d
                break
        
        # Если не нашли ни комнату, ни устройство, это может быть общая команда
        if not device and not room:
            # Проверим, может быть это общая команда вроде "выключи все"
            if "все" in text_lower:
                if action == "turn_off":
                    self.log("Выключаю все устройства умного дома")
                    self.speak("Выключаю все устройства")
                    # Здесь можно добавить логику выключения всех устройств
                    return True
        
        # Пытаемся найти конкретное устройство по комнате и типу
        if room and device:
            # Ищем зарегистрированное устройство
            devices_in_room = self.smart_home.get_devices_by_room(room)
            matching_devices = {id: dev for id, dev in devices_in_room.items() if device in dev["name"].lower()}
            
            if matching_devices:
                device_id = list(matching_devices.keys())[0]  # Берем первое совпадение
                if action == "turn_on":
                    self.smart_home.turn_on(device_id)
                    self.speak(f"Включаю {device} в {room}")
                elif action == "turn_off":
                    self.smart_home.turn_off(device_id)
                    self.speak(f"Выключаю {device} в {room}")
                elif action == "toggle":
                    self.smart_home.toggle(device_id)
                    self.speak(f"Переключаю {device} в {room}")
                return True
            else:
                self.speak(f"Не найдено устройство {device} в {room}")
                return True
        
        # Если нашли устройство без комнаты
        elif device:
            # Ищем устройство по типу
            devices_by_type = self.smart_home.get_devices_by_type(device)
            if devices_by_type:
                device_id = list(devices_by_type.keys())[0]  # Берем первое совпадение
                if action == "turn_on":
                    self.smart_home.turn_on(device_id)
                    self.speak(f"Включаю {device}")
                elif action == "turn_off":
                    self.smart_home.turn_off(device_id)
                    self.speak(f"Выключаю {device}")
                elif action == "toggle":
                    self.smart_home.toggle(device_id)
                    self.speak(f"Переключаю {device}")
                return True
            else:
                self.speak(f"Не найдено устройство {device}")
                return True
        
        return False

    def _listen_loop(self):
        if not self.mic:
            self.log("🎙 Микрофон недоступен. Голосовое управление отключено.")
            return

        # Initial adjustment and parameters (Matching PyQt6)
        try:
            with self.mic as source:
                # Adjust settings based on performance mode
                self.adjust_performance_mode()
                self.recognizer.non_speaking_duration = 0.8
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                self.log(f"🎤 Микрофон готов (порог: {int(self.recognizer.energy_threshold)}, режим: {self.settings.get('performance_mode')})")
        except Exception as e:
            self.log(f"⚠ Сбой настройки микрофона: {e}")

        while True:
            if not self.is_listening or self.dictation_active:
                # В зависимости от режима производительности, изменяем частоту проверок
                time.sleep(0.5 / getattr(self, 'performance_factor', 1.0))
                continue

            try:
                with self.mic as source:
                    # Just listen normally
                    audio = self.recognizer.listen(source, timeout=3, phrase_time_limit=10)
                    text = self._recognize_speech(audio)
                    if text:
                        text = text.lower()
                    else:
                        continue

                    if any(w in text for w in ["джарвис", "jarvis", "жарвис"]):
                        text = re.sub(r'джарвис|jarvis|жарвис', '', text).strip()
                        self.log(f"→ Услышал: {text}")
                        try: eel.add_chat_message("YOU", text)()
                        except: pass

                        if text:
                            self.process_command(text)
                        else:
                            self.speak("Слушаю, сэр.")

                        self.last_activity_time = time.time()
            except sr.WaitTimeoutError: pass
            except sr.UnknownValueError: pass
            except Exception as e:
                if self.is_listening: self.log(f"Микрофон: {e}")
                time.sleep(1 / getattr(self, 'performance_factor', 1.0))

    def _recognize_speech(self, audio: sr.AudioData) -> str:
        """Распознавание речи. Приоритет: Vosk (оффлайн) -> Google (если Vosk выключен/не готов)."""
        # 1) Vosk offline
        if self.settings.get("use_vosk") and self.vosk_failed_attempts < self.max_vosk_failures:
            try:
                from vosk import Model, KaldiRecognizer
                model_path = self.settings.get("vosk_model_path") or str(VOSK_MODEL_DIR)
                model_path = str(model_path)
                if not Path(model_path).exists():
                    self._log_once("vosk_missing", f"⚠ Vosk модель не найдена: {model_path}")
                    # Переходим к Google STT как резервному варианту
                else:
                    # Проверяем, содержит ли папка необходимые файлы модели
                    required_files = ['am/final.mdl', 'conf/mfcc.conf', 'conf/model.conf']
                    missing_files = []
                    for req_file in required_files:
                        if not Path(model_path, req_file).exists():
                            missing_files.append(req_file)
                    
                    if missing_files:
                        self._log_once("vosk_incomplete", f"⚠ Vosk модель неполная, отсутствуют файлы: {missing_files}")
                        # Переходим к Google STT как резервному варианту
                    else:
                        try:
                            # Пытаемся создать модель Vosk
                            abs_model_path = Path(model_path).resolve()
                            self.log(f"🔧 Загрузка Vosk модели из: {abs_model_path}")
                            model = Model(str(abs_model_path))
                            self.log("✅ Модель Vosk загружена успешно")
                            self.vosk_failed_attempts = 0  # Сброс счетчика при успешной загрузке
                            
                            # Vosk любит 16kHz 16-bit mono
                            pcm = audio.get_raw_data(convert_rate=16000, convert_width=2)
                            rec = KaldiRecognizer(model, 16000)
                            rec.SetWords(True)
                            rec.AcceptWaveform(pcm)
                            data = json.loads(rec.FinalResult() or "{}")
                            txt = (data.get("text") or "").strip()
                            
                            self.log(f"📝 Результат Vosk: {txt}")
                            
                            # Мини-оценка уверенности по словам (если есть)
                            words = data.get("result") or []
                            if words:
                                avg_conf = sum(w.get("conf", 1.0) for w in words) / max(len(words), 1)
                                min_conf = float(self.settings.get("vosk_min_conf", 0.60))
                                if avg_conf < min_conf:
                                    self._log_once("vosk_low_conf", f"⚠ Vosk низкая уверенность ({avg_conf:.2f}).")
                                    return ""
                            return txt
                        except Exception as model_error:
                            self.vosk_failed_attempts += 1
                            self.log(f"❌ Ошибка создания модели Vosk (попытка {self.vosk_failed_attempts}/{self.max_vosk_failures}): {model_error}")
                            # Выводим более подробную информацию об ошибке
                            import traceback
                            self.log(f"📋 Трассировка ошибки: {traceback.format_exc()}")
                            
                            # Проверим, может быть проблема в структуре файлов модели
                            try:
                                import os
                                self.log(f"📁 Структура папки модели: {os.listdir(model_path)}")
                                if os.path.exists(os.path.join(model_path, "am")):
                                    self.log(f"📁 Содержимое am/: {os.listdir(os.path.join(model_path, 'am'))}")
                                if os.path.exists(os.path.join(model_path, "conf")):
                                    self.log(f"📁 Содержимое conf/: {os.listdir(os.path.join(model_path, 'conf'))}")
                            except Exception as struct_error:
                                self.log(f"📋 Ошибка при проверке структуры модели: {struct_error}")
                            
                            # Если достигнут лимит неудачных попыток, отключаем Vosk
                            if self.vosk_failed_attempts >= self.max_vosk_failures:
                                self.log("❌ Достигнут лимит неудачных попыток загрузки Vosk. Отключаю использование Vosk.")
                                self.settings["use_vosk"] = False
                                self.save_json(EXE_BASE / "jarvis_settings.json", self.settings)
                            
                            # Переходим к Google STT как резервному варианту
            except Exception as e:
                self.vosk_failed_attempts += 1
                self.log(f"❌ Общая ошибка Vosk (попытка {self.vosk_failed_attempts}/{self.max_vosk_failures}): {e}")
                import traceback
                self.log(f"📋 Трассировка общей ошибки: {traceback.format_exc()}")
                
                # Если достигнут лимит неудачных попыток, отключаем Vosk
                if self.vosk_failed_attempts >= self.max_vosk_failures:
                    self.log("❌ Достигнут лимит неудачных попыток загрузки Vosk. Отключаю использование Vosk.")
                    self.settings["use_vosk"] = False
                    self.save_json(EXE_BASE / "jarvis_settings.json", self.settings)
                
                # Переходим к Google STT как резервному варианту

        # 2) Google (онлайн фолбэк) - теперь с учетом языка STT
        try:
            return self.recognizer.recognize_google(audio, language="ru-RU").strip()
        except Exception:
            return ""

    def process_command(self, text):
        text = (text or "").strip()
        if not text:
            return

        # Обработка в режиме обучения
        if self.learning_mode:
            self._process_learning_input(text)
            return

        # Команда активации режима обучения
        if any(kw in text for kw in ["режим обучения", "обучи меня", "новая команда"]):
            self._enter_learning_mode()
            return

        # Обработка команд умного дома
        if self._process_smart_home_command(text):
            return

        # 0.0 Confirmation handling
        if self.pending_confirmation and self.settings.get("confirm_dangerous", True):
            t = text.lower().strip()
            if any(x in t for x in ["да", "подтверждаю", "ок", "хорошо", "давай"]):
                pending = self.pending_confirmation
                self.pending_confirmation = None
                kind = pending.get("kind")
                payload = pending.get("payload") or {}
                if kind == "shutdown":
                    self.speak("Подтверждено. Выключаюсь.")
                    time.sleep(1)
                    os._exit(0)
                if kind == "custom":
                    # повторяем исполнение кастом-команды
                    cmd_text = payload.get("text") or ""
                    self._run_custom_command(cmd_text)
                    return
            if any(x in t for x in ["нет", "отмена", "не надо", "стоп"]):
                self.pending_confirmation = None
                self.speak("Отменено.")
                return

        # 0. Interruption — остановка речи (как в jarvis_fixed)
        if any(w in text for w in ["стоп", "stop", "хватит", "молчать", "замолчи", "тихо"]):
            self.stop_speech()
            return

        # 0.1 Scene trigger
        low = text.lower().strip()
        if low.startswith("сцена ") or low.startswith("режим "):
            name = low.split(" ", 1)[1].strip()
            if self._run_scene(name):
                return

        # 1. Dictation Mode
        # Поддерживаем разные формы: "диктовка", "диктовки", "режим диктовки"
        if any(kw in text for kw in ["диктовка", "диктовк", "печатай"]):
            self.speak("Режим диктовки активирован")
            self.dictation_active = True
            threading.Thread(target=self._dictation_worker, daemon=True).start()
            return

        # 2. Basic Built‑in Commands
        if "время" in text or "час" in text:
            now = datetime.datetime.now().strftime("%H:%M")
            self.speak(f"Сейчас {now}")
        elif "ютуб" in text:
            self.speak("Открываю Ютуб")
            webbrowser.open("https://youtube.com")
        elif self._run_system_intents(text):
            return
        elif "экран" in text or "что видишь" in text:
            self.speak("Смотрю...")
            threading.Thread(target=self._analyze_screen, daemon=True).start()
        elif "выключись" in text:
            if self.settings.get("confirm_dangerous", True):
                self.pending_confirmation = {"kind": "shutdown", "payload": {}}
                self.speak("Подтвердите выключение: скажите 'да' или 'отмена'.")
                return
            else:
                self.speak("До встречи, сэр")
                time.sleep(1)
                os._exit(0)
        else:
            # 3. Custom User Commands
            if self._run_custom_command(text):
                return
            # 4. AI Brain
            if self.settings.get("use_llama"):
                self.speak("Обрабатываю запрос")
                threading.Thread(target=self.ask_ai, args=(text,), daemon=True).start()
            else:
                self.speak("Не понял команду.")

    def _run_system_intents(self, text: str) -> bool:
        """Быстрые системные действия без ИИ."""
        t = (text or "").lower().strip()
        # Volume
        if any(x in t for x in ["громче", "прибавь звук", "увеличь громкость"]):
            return self._run_system_action("volume_up")
        if any(x in t for x in ["тише", "убавь звук", "уменьши громкость"]):
            return self._run_system_action("volume_down")
        if any(x in t for x in ["выключи звук", "мут", "mute", "без звука"]):
            return self._run_system_action("mute")
        
        # Media Control
        if any(x in t for x in ["играй", "плей", "пуск", "продолжи", "на паузу", "пауза", "play", "pause"]):
            return self._run_system_action("play_pause")
        if any(x in t for x in ["следующий", "некст", "вперед", "next"]):
            return self._run_system_action("next_track")
        if any(x in t for x in ["предыдущий", "назад", "prev"]):
            return self._run_system_action("prev_track")

        # Open website quick
        if t.startswith("открой сайт "):
            q = t.split("открой сайт ", 1)[1].strip()
            if q and not q.startswith("http"):
                q = "https://" + q
            webbrowser.open(q)
            self._play_random_custom_sound()
            return True
        # Screenshot
        if any(x in t for x in ["скриншот", "снимок экрана"]):
            try:
                p = CACHE_DIR / f"screenshot_{int(time.time())}.png"
                pyautogui.screenshot(str(p))
                self._play_random_custom_sound()
                self.log(f"Скриншот сохранён: {p}")
                return True
            except Exception as e:
                self.log(f"Ошибка скриншота: {e}")
                return True

        # Clipboard read
        if any(x in t for x in ["что в буфере", "прочитай буфер", "буфер обмена"]):
            try:
                val = pyperclip.paste()
                val = (val or "").strip()
                if not val:
                    self.speak("Буфер пуст.")
                else:
                    # не озвучиваем гигантские тексты
                    self.speak(val[:300])
                return True
            except Exception as e:
                self.log(f"Ошибка буфера: {e}")
                return True

        # Type last clipboard
        if any(x in t for x in ["вставь", "вставить из буфера"]):
            try:
                keyboard.write(pyperclip.paste() or "")
                self._play_random_custom_sound()
                return True
            except Exception as e:
                self.log(f"Ошибка вставки: {e}")
                return True
        return False

    def _run_system_action(self, action: str) -> bool:
        try:
            a = (action or "").lower().strip()
            if a == "volume_up":
                pyautogui.press("volumeup")
            elif a == "volume_down":
                pyautogui.press("volumedown")
            elif a == "mute":
                pyautogui.press("volumemute")
            elif a == "next_track":
                pyautogui.press("nexttrack")
            elif a == "prev_track":
                pyautogui.press("prevtrack")
            elif a == "play_pause":
                pyautogui.press("playpause")
            else:
                self.log(f"Неизвестное системное действие: {action}")
                return False
            # Звук подтверждения — в фоне, чтобы не блокировать
            threading.Thread(target=self._play_random_custom_sound, daemon=True).start()
            return True
        except Exception as e:
            self.log(f"Ошибка системного действия '{action}': {e}")
            return False

    def _run_custom_command(self, text):
        """Пытается выполнить пользовательскую команду из jarvis_cmds.json.
        Возвращает True, если что‑то было выполнено."""
        if not self.cmds:
            return False

        def _norm(s: str) -> str:
            s = (s or "").lower().strip()
            s = s.replace("ё", "е")
            s = re.sub(r"\s+", " ", s)
            return s

        t = _norm(text)

        def _compile_pattern(pat: str):
            """Поддержка шаблонов вида: 'открой сайт {q}' -> regex с группами."""
            pat_n = _norm(pat)
            if "{" not in pat_n or "}" not in pat_n:
                return None
            # {name} => (?P<name>.+)
            # экранируем всё кроме плейсхолдеров
            parts = []
            i = 0
            while i < len(pat_n):
                if pat_n[i] == "{":
                    j = pat_n.find("}", i + 1)
                    if j == -1:
                        break
                    name = pat_n[i + 1:j].strip() or "arg"
                    name = re.sub(r"[^\w]", "", name) or "arg"
                    parts.append(f"(?P<{name}>.+)")
                    i = j + 1
                else:
                    parts.append(re.escape(pat_n[i]))
                    i += 1
            rx = "".join(parts)
            rx = rx.replace(r"\ ", r"\s+")
            return re.compile(rf"^{rx}$", re.IGNORECASE)

        def _render_action(action: str, params: dict):
            try:
                return str(action).format(**params)
            except Exception:
                return action

        # 1. Прямое совпадение
        cfg = self.cmds.get(t) or self.cmds.get(text.lower().strip())

        # 1.1 Шаблоны с параметрами (regex)
        matched_params = None
        matched_key = None
        if not cfg:
            for key, val in self.cmds.items():
                rx = _compile_pattern(key)
                if not rx:
                    continue
                m = rx.match(t)
                if m:
                    cfg = val
                    matched_params = {k: v.strip() for k, v in m.groupdict().items() if v}
                    matched_key = key
                    break

        # 2. Поиск по вхождению ключевой фразы
        if not cfg:
            for key, val in self.cmds.items():
                if _norm(key) in t:
                    cfg = val
                    break

        # 3. Нечёткое совпадение (полезно при ошибках STT: "запрет" vs "заперт")
        if not cfg:
            keys = list(self.cmds.keys())
            norm_map = {_norm(k): k for k in keys}
            matches = difflib.get_close_matches(t, list(norm_map.keys()), n=1, cutoff=0.78)
            if matches:
                best_norm = matches[0]
                best_key = norm_map.get(best_norm)
                if best_key:
                    cfg = self.cmds.get(best_key)

        if not cfg:
            return False

        action = cfg.get("action")
        action_type = cfg.get("action_type", "program")
        if not action:
            return False

        # Если команда шаблонная — подставляем параметры в action
        if matched_params and isinstance(action, str):
            action = _render_action(action, matched_params)

        try:
            if action_type == "program":
                # Запуск внешней программы/файла
                subprocess.Popen(action, shell=True)
                self._play_random_custom_sound()
            elif action_type == "text":
                # Вставка текста (например, шаблон)
                pyperclip.copy(action)
                keyboard.write(action)
                self._play_random_custom_sound()
            elif action_type == "url":
                webbrowser.open(str(action))
                self._play_random_custom_sound()
            elif action_type == "scene":
                # action = имя сцены
                return self._run_scene(str(action))
            else:
                self.log(f"Неизвестный тип команды: {action_type}")
                return False
            return True
        except Exception as e:
            self.log(f"Ошибка выполнения команды '{text}': {e}")
            self.speak("Произошла ошибка при выполнении команды.")
            return False

    def _run_scene(self, name: str) -> bool:
        name = (name or "").strip().lower()
        # поддержка "scene: имя" и прямого имени
        if name.startswith("scene:"):
            name = name.split(":", 1)[1].strip()
        scene = self.scenes.get(name) or self.scenes.get(name.lower())
        if not scene:
            self.log(f"Сцена не найдена: {name}")
            return False
        try:
            def exec_action(action_type: str, action):
                if not action:
                    return
                action_type = (action_type or "program").lower()
                if action_type == "program":
                    subprocess.Popen(str(action), shell=True)
                elif action_type == "url":
                    webbrowser.open(str(action))
                elif action_type == "text":
                    pyperclip.copy(str(action))
                    keyboard.write(str(action))
                elif action_type == "command":
                    self.process_command(str(action))
                elif action_type == "system":
                    self._run_system_action(str(action))
                else:
                    self.log(f"Неизвестный тип действия сцены: {action_type}")

            # scene может быть списком действий или объектом {"actions":[...], "settings":{...}}
            settings_patch = scene.get("settings") if isinstance(scene, dict) else None
            actions = scene.get("actions") if isinstance(scene, dict) else scene
            if settings_patch and isinstance(settings_patch, dict):
                self.settings.update(settings_patch)
                self.save_json(EXE_BASE / "jarvis_settings.json", self.settings)
            if actions and isinstance(actions, list):
                for act in actions:
                    if not act:
                        continue
                    if isinstance(act, str):
                        self.process_command(act)
                    elif isinstance(act, dict):
                        # прямой запуск: {"type":"program","action":"..."} или {"action_type":"url","action":"..."}
                        at = act.get("action_type") or act.get("type") or "program"
                        aa = act.get("action") or act.get("value")
                        exec_action(at, aa)
            self._play_random_custom_sound()
            return True
        except Exception as e:
            self.log(f"Ошибка сцены '{name}': {e}")
            return False

    def _dictation_worker(self):
        """Отдельный поток диктовки: используем собственный источник микрофона,
        чтобы не конфликтовать с основным циклом прослушивания."""
        try:
            import speech_recognition as sr
            with sr.Microphone() as src:
                while self.dictation_active:
                    try:
                        audio = self.recognizer.listen(src, timeout=2, phrase_time_limit=5)
                        txt = self.recognizer.recognize_google(audio, language="ru-RU").lower()
                        if "стоп диктовка" in txt or "хватит" in txt:
                            self.dictation_active = False
                            self.speak("Диктовка завершена")
                            break
                        keyboard.write(txt + " ")
                    except Exception:
                        pass
        except Exception as e:
            self.log(f"Ошибка режима диктовки: {e}")
            self.dictation_active = False

    def _analyze_screen(self):
        if not OCR_AVAILABLE:
            self.speak("Система зрения не инициализирована")
            return
        try:
            screenshot_path = CACHE_DIR / "temp_screen.png"
            pyautogui.screenshot(str(screenshot_path))
            img = cv2.imread(str(screenshot_path))
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            screen_text = pytesseract.image_to_string(gray, lang='rus+eng')
            self.log(f"Контекст экрана: {screen_text[:100]}...")
            self.ask_ai(f"На экране написано: {screen_text}. Проанализируй это.")
        except Exception as e:
            self.log(f"Ошибка зрения: {e}")

    JARVIS_BRIEF_INSTRUCTIONS = (
        "Ты JARVIS — голосовой ассистент в стиле фильма Iron Man. "
        "Отвечай СТРОГО 2–3 короткими предложениями. "
        "Каждый ответ ОБЯЗАТЕЛЬНО начинай со слова «Сэр» (например: «Сэр, …»). "
        "Без списков, заголовков и markdown. Только русский язык."
    )

    def _format_jarvis_reply(self, text):
        """Краткий ответ в стиле JARVIS: начинается с «Сэр», не более 3 предложений."""
        if not text:
            return "Сэр, не могу ответить."
        text = str(text).strip()
        text = re.sub(r'^#{1,6}\s*', '', text, flags=re.M)
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'\n+', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        parts = re.split(r'(?<=[.!?…])\s+', text)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) > 5:
            text = ' '.join(parts[:5])
            if text and text[-1] not in '.!?…':
                text += '.'
        elif parts:
            text = ' '.join(parts)

        if not re.match(r'^сэр\b', text, re.IGNORECASE):
            text = text.lstrip(',').strip()
            text = f"Сэр, {text}" if text else "Сэр."
        else:
            text = re.sub(r'^сэр\b', 'Сэр', text, flags=re.IGNORECASE)

        return text

    def _parse_yandex_response(self, data):
        """Текст из ответа Agents API (responses)."""
        content = (data.get("output_text") or "").strip()
        if content:
            return content
        for item in data.get("output") or []:
            if item.get("type") != "message":
                continue
            for part in item.get("content") or []:
                if part.get("type") == "output_text":
                    content = (part.get("text") or "").strip()
                    if content:
                        return content
        return None

    def _ask_yandex_ai(self, text):
        """Генерация через Yandex AI Studio (агент или chat/completions)."""
        import urllib.request
        import urllib.error

        self._yandex_last_http = None
        api_key = (
            self.settings.get("yandex_api_key")
            or os.environ.get("YANDEX_API_KEY")
            or os.environ.get("YC_API_KEY")
            or ""
        ).strip()
        folder_id = (
            self.settings.get("yandex_folder_id")
            or os.environ.get("YANDEX_FOLDER_ID")
            or os.environ.get("YC_FOLDER_ID")
            or ""
        ).strip()
        agent_id = (self.settings.get("yandex_agent_id") or "").strip()

        if not api_key:
            self.log("⚠ Yandex API key не задан.")
            return None
        if not folder_id:
            self.log("⚠ Yandex folder_id не задан.")
            return None

        headers = {
            "Authorization": f"Api-Key {api_key}",
            "Content-Type": "application/json",
            "x-folder-id": folder_id,
        }

        max_turns = int(self.settings.get("memory_max_turns", 6))
        mem = (self.chat_memory or [])[-(max_turns * 2):]
        context_lines = []
        for m in mem:
            role = m.get("role")
            content = (m.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                prefix = "Пользователь" if role == "user" else "Ассистент"
                context_lines.append(f"{prefix}: {content}")
        user_input = text
        if context_lines:
            user_input = "\n".join(context_lines) + f"\nПользователь: {text}"
        user_input = (
            "[Ответь ровно 2–3 короткими предложениями. Начни с «Сэр». Без markdown.]\n"
            + user_input
        )

        # 1) Агент из AI Studio (как в коде на скриншоте)
        if agent_id:
            payload = json.dumps({
                "prompt": {"id": agent_id},
                "input": user_input,
                "instructions": self.JARVIS_BRIEF_INSTRUCTIONS,
                "max_output_tokens": 120,
            }, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                "https://ai.api.cloud.yandex.net/v1/responses",
                data=payload,
                method="POST",
                headers=headers,
            )
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                content = self._parse_yandex_response(data)
                if content:
                    return self._format_jarvis_reply(content)
                err = data.get("error")
                if err:
                    self.log(f"⚠ Yandex Agent error: {err}")
            except urllib.error.HTTPError as e:
                err_body = ""
                try:
                    err_body = e.read().decode("utf-8", errors="replace")[:500]
                except Exception:
                    pass
                self._yandex_last_http = e.code
                self.log(f"⚠ Yandex Agent HTTP {e.code}: {err_body}")
            except Exception as e:
                self.log(f"⚠ Yandex Agent: {e}")

        # 2) Fallback: chat/completions + YandexGPT
        model_name = (self.settings.get("yandex_model") or "yandexgpt").strip()
        model_version = (self.settings.get("yandex_model_version") or "latest").strip()
        model_uri = f"gpt://{folder_id}/{model_name}/{model_version}"
        messages = [
            {"role": "system", "content": self.JARVIS_BRIEF_INSTRUCTIONS}
        ]
        for m in mem:
            role = m.get("role")
            content = (m.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": text})

        payload = json.dumps({
            "model": model_uri,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 120,
        }, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            "https://llm.api.cloud.yandex.net/v1/chat/completions",
            data=payload,
            method="POST",
            headers=headers,
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                content = (msg.get("content") or "").strip()
                if content:
                    return self._format_jarvis_reply(content)
            raise ValueError("Пустой ответ от Yandex AI Studio")
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            self._yandex_last_http = e.code
            self.log(f"⚠ Yandex HTTP {e.code}: {err_body}")
            return None
        except Exception as e:
            self.log(f"⚠ Yandex AI: {e}")
            return None

    def _ask_qwen_cli(self, text):
        """Интеграция с локальной CLI 'qwen' (Qwen Code v0.10.6)."""
        import shutil
        try:
            self.log(f"💻 Поиск Qwen CLI...")
            qwen_path = shutil.which("qwen")
            if not qwen_path:
                appdata = os.environ.get("APPDATA", "")
                npm_path = Path(appdata) / "npm" / "qwen.cmd"
                if npm_path.exists():
                    qwen_path = str(npm_path)
            
            if not qwen_path:
                self.log("⚠ Команда 'qwen' не найдена в системе.")
                return "Сэр, команда 'qwen' не найдена. Убедитесь, что Qwen Code установлен."

            self.log(f"💻 Вызов {qwen_path}...")
            
            output = ""
            last_proc = None

            # Add conciseness instruction if not a warm-up
            if "привет" not in text.lower() or len(text) > 10:
                text_with_instr = f"{text}. Отвечай кратко, в 2-3 предложениях."
            else:
                text_with_instr = text

            # 1. Пробуем передать как аргумент
            try:
                self.log(f"⌛ Попытка 1 (аргумент), таймаут 60с...")
                start_t = time.time()
                last_proc = subprocess.run(
                    [qwen_path, text_with_instr], 
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    timeout=60
                )
                self.log(f"✅ Процесс завершен за {time.time() - start_t:.1f}с")
                if last_proc.stdout and len(last_proc.stdout.strip()) > 5:
                    output = last_proc.stdout
                if last_proc.stderr:
                    self.log(f"📋 Qwen Stderr: {last_proc.stderr[:100]}...")
            except subprocess.TimeoutExpired:
                self.log("⚠ Таймаут первой попытки (60с)")
            except Exception as e:
                self.log(f"ℹ Первая попытка не удалась: {e}")

            # 2. Если аргумент не сработал — пробуем через stdin
            if not output.strip():
                try:
                    self.log(f"⌛ Попытка 2 (stdin), таймаут 60с...")
                    start_t = time.time()
                    last_proc = subprocess.run(
                        [qwen_path], 
                        shell=True,
                        input=f"{text_with_instr}\n".encode('utf-8'),
                        capture_output=True,
                        timeout=60
                    )
                    self.log(f"✅ Процесс (stdin) завершен за {time.time() - start_t:.1f}с")
                    stdout = last_proc.stdout.decode('utf-8', errors='ignore')
                    stderr = last_proc.stderr.decode('utf-8', errors='ignore')
                    output = stdout + "\n" + stderr
                    if stderr:
                        self.log(f"📋 Qwen Stderr (stdin): {stderr[:100]}...")
                except subprocess.TimeoutExpired:
                    self.log("⚠ Таймаут второй попытки (60с)")
                except Exception as e:
                    self.log(f"ℹ Вторая попытка не удалась: {e}")

            # Очистка
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            filtered = []
            for line in lines:
                if any(x in line for x in ["Введите сообщение", "Qwen Code", "Tips:", "auth type", "home directory", ">_"]):
                    continue
                # Убираем эхо нашего вопроса
                if text.lower() in line.lower() and len(line) < len(text) + 20:
                    continue
                filtered.append(line)
            
            if not filtered:
                # Если ничего не нашли, но процесс завершился — возможно, нужен логин
                status = f"Код: {last_proc.returncode}" if last_proc else "Таймаут"
                self.log(f"⚠ Qwen CLI вернул пустой результат. {status}")
                return "Сэр, Qwen CLI не ответил. Попробуйте один раз запустить его вручную в консоли и убедитесь, что вы авторизованы."
                
            return "\n".join(filtered)
            
        except Exception as e:
            self.log(f"⚠ Критическая ошибка вызова qwen CLI: {e}")
            return f"Ошибка системы: {str(e)[:50]}"

    def ask_ai(self, text):
        # 0. Приоритет: Локальный CLI (Qwen Code), если включен
        if self.settings.get("use_qwen_cli"):
            response = self._ask_qwen_cli(text)
            if response:
                # Если получили ответ от CLI, пропускаем остальную логику генерации
                pass
            else:
                response = ""
        else:
            response = ""

        # 1. Режим ИИ: либо онлайн, либо оффлайн (только если еще нет ответа)
        use_online = False
        if not response:
            use_online = self.settings.get("use_online_ai", True)
        
        if response:
            # Если ответ уже есть (от CLI), просто пропускаем генерацию
            pass
        elif use_online:
            if (self.settings.get("yandex_agent_id") or "").strip():
                self.log("🌐 Запрос к агенту Yandex AI Studio...")
            else:
                self.log("🌐 Генерация через Yandex AI Studio...")
            response = self._ask_yandex_ai(text)
            if not response:
                api_key = (self.settings.get("yandex_api_key") or "").strip()
                folder_id = (self.settings.get("yandex_folder_id") or "").strip()
                if not api_key:
                    response = "Сэр, укажите API-ключ Yandex AI Studio в настройках."
                elif not folder_id:
                    response = (
                        "Сэр, укажите Folder ID каталога Yandex Cloud в настройках "
                        "(консоль cloud.yandex.ru → селектор каталога → ID вида b1g...)."
                    )
                elif getattr(self, "_yandex_last_http", None) == 403:
                    response = (
                        "Сэр, у API-ключа нет прав на Yandex AI. "
                        "Создайте новый ключ в AI Studio: область yc.ai.languageModels.execute, "
                        f"каталог {folder_id}, и включён биллинг."
                    )
                elif getattr(self, "_yandex_last_http", None) == 401:
                    response = "Сэр, API-ключ Yandex недействителен. Создайте новый ключ в AI Studio."
                else:
                    self.log("⚠ Yandex AI не ответил. Пробую локальный режим...")
                    use_online = False

        if not response and not use_online:
            if self.settings.get("use_qwen_llm"):
                # Если Qwen ещё не загружена — пробуем запустить загрузку по запросу
                if not self.qwen_llm_model:
                    if not self.qwen_llm_loading:
                        self._load_qwen_llm()
                        self.log("🧠 Локальная модель Qwen загружается по запросу...")
                    response = "Сэр, локальный мозг ещё загружается. Повторите запрос через несколько секунд."
                else:
                    self.log("🧠 Генерация Qwen 2.5...")
                    
                    # Память: добавляем несколько последних реплик, чтобы был контекст
                    max_turns = int(self.settings.get("memory_max_turns", 6))
                    # 1 turn = user+assistant, поэтому берём 2*max_turns сообщений
                    mem = (self.chat_memory or [])[-(max_turns * 2):]
                    
                    prompt = (
                        "<|im_start|>system\n"
                        + self.JARVIS_BRIEF_INSTRUCTIONS
                        + "<|im_end|>\n"
                    )
                    
                    for m in mem:
                        role = m.get("role")
                        content = (m.get("content") or "").strip()
                        if not content:
                            continue
                        if role == "user":
                            prompt += f"<|im_start|>user\n{content}<|im_end|>\n"
                        else:
                            prompt += f"<|im_start|>assistant\n{content}<|im_end|>\n"

                    prompt += f"<|im_start|>user\n{text}<|im_end|>\n<|im_start|>assistant\n"

                    output = self.qwen_llm_model(prompt, max_tokens=150, temperature=0.3, stop=["<|im_end|>"])
                    response = output['choices'][0]['text'].strip()
            else:
                # ИИ в настройках отключен
                self.log("⚙ ИИ полностью отключён в настройках.")
                response = "Сэр, ИИ сейчас отключён. Включите Онлайн или Локальный режим в настройках."

        if response:
            response = self._format_jarvis_reply(response)
        
        # сохраняем память (даже если TTS выключен)
        try:
            self.chat_memory.append({"role": "user", "content": str(text)})
            self.chat_memory.append({"role": "assistant", "content": str(response)})
            # ограничение памяти
            max_turns = int(self.settings.get("memory_max_turns", 6))
            self.chat_memory = self.chat_memory[-(max_turns * 2):]
            self.save_json(MEMORY_PATH, self.chat_memory)
        except Exception as e:
            self._log_once("memory_save", f"⚠ Не удалось сохранить память: {e}")

        self.speak(response)
        try: eel.show_response(response)()
        except Exception as e:
            # UI может быть не готово; не спамим, но оставим 1 предупреждение
            self._log_once("eel_show_response", f"⚠ UI не принял ответ: {e}")

    def _load_cosyvoice(self):
        if getattr(self, "cosyvoice_loading", False) or getattr(self, "cosyvoice_ready", False): return
        self.cosyvoice_loading = True
        
        mode = self.settings.get("cosyvoice_mode", "local")
        if mode == "api":
            self.log("🔌 Подключение к CosyVoice API...")
            def api_checker():
                try:
                    import urllib.request
                    api_url = self.settings.get("cosyvoice_api_url", "http://127.0.0.1:9880")
                    url = f"{api_url}/tts" if not api_url.endswith("/tts") else api_url
                    
                    # Пытаемся сделать быстрый GET/POST запрос для проверки связи
                    req = urllib.request.Request(api_url, method="GET")
                    with urllib.request.urlopen(req, timeout=3) as _:
                        pass
                    self.log(f"✅ Успешно подключено к CosyVoice API ({api_url})")
                    self.cosyvoice_ready = True
                    self.cosyvoice_api_confirmed = True
                    self.speak("Голосовая система Кози Войс подключена через внешнее API.")
                except Exception as e:
                    # Сервер недоступен — не помечаем как готовый, будет переключение на Edge TTS
                    self.log(f"🔌 CosyVoice API недоступен ({self.settings.get('cosyvoice_api_url', 'http://127.0.0.1:9880')}). Запустите cosyvoice_start.bat для активации.")
                    self.cosyvoice_ready = False
                    self.cosyvoice_api_confirmed = False
                finally:
                    self.cosyvoice_loading = False
            threading.Thread(target=api_checker, daemon=True).start()
            return

        self.log("⬇ Загрузка локального CosyVoice (Voice Clone)...")
        def loader():
            try:
                import sys
                import subprocess
                flags = 0x08000000 if os.name == 'nt' else 0
                
                # Check / install dependencies
                try:
                    import cosyvoice
                    from cosyvoice.cli.cosyvoice import CosyVoice
                except (ImportError, ModuleNotFoundError):
                    self.log("📦 Обнаружена некорректная или отсутствующая версия CosyVoice. Пытаюсь переустановить...")
                    subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "cosyvoice"], creationflags=flags)
                    self.log("📦 Установка официального CosyVoice с GitHub...")
                    subprocess.run([sys.executable, "-m", "pip", "install", "git+https://github.com/FunAudioLLM/CosyVoice.git"], creationflags=flags)
                
                # Verify import works now
                from cosyvoice.cli.cosyvoice import CosyVoice
                
                # Model selection and downloading
                model_name = self.settings.get("cosyvoice_model", "FunAudioLLM/CosyVoice-300M-Instruct")
                local_model_dir = EXE_BASE / "cosyvoice_models" / model_name.split("/")[-1]
                
                if not local_model_dir.exists():
                    self.log(f"🔍 Загрузка модели CosyVoice: {model_name}...")
                    from huggingface_hub import snapshot_download
                    
                    def log_tqdm_factory(*args, **kwargs):
                        from tqdm.auto import tqdm
                        t = tqdm(*args, **kwargs)
                        t._last_p = -1
                        original_display = t.display
                        def custom_display(msg=None, pos=None):
                            if t.total:
                                p = int(t.n * 100 / t.total)
                                if p != t._last_p and p % 10 == 0:
                                    self.log(f"⬇ Загрузка модели: {p}%")
                                    t._last_p = p
                            return original_display(msg, pos)
                        t.display = custom_display
                        return t

                    snapshot_download(repo_id=model_name, local_dir=local_model_dir, tqdm_class=log_tqdm_factory)
                
                self.log("🧠 Инициализация CosyVoice...")
                self.cosyvoice_model = CosyVoice(str(local_model_dir))
                self.cosyvoice_ready = True
                self.log("✅ CosyVoice успешно загружен!")
                self.speak("Голосовая система Кози Войс готова.")
            except Exception as e:
                self.log(f"❌ Ошибка локальной загрузки CosyVoice: {e}")
                self.log("💡 Подсказка: Локальный запуск CosyVoice требует сложных C++ библиотек (pynini/onnx/torchaudio), которые трудно скомпилировать на Windows.")
                self.log("👉 РЕКОМЕНДУЕТСЯ: Переключите 'Режим CosyVoice' в настройках на 'Внешний сервер (API)' и запустите любой готовый дистрибутив CosyVoice API (например, на порту 9880).")
                self.speak("Сэр, локальный запуск Кози Войс не удался. Рекомендую переключить режим на внешнее апи.")
                self.log_exception("CosyVoice Loader")
            finally:
                self.cosyvoice_loading = False
                
        threading.Thread(target=loader, daemon=True).start()

    def _generate_cosyvoice(self, text, path):
        # Если включен режим API
        if self.settings.get("cosyvoice_mode") == "api":
            return self._generate_cosyvoice_api(text, path)
            
        if not getattr(self, "cosyvoice_ready", False) or not getattr(self, "cosyvoice_model", None):
            # Пытаемся лениво загрузить
            self._load_cosyvoice()
            return False
            
        try:
            import torchaudio
            import torch
            from cosyvoice.utils.file_utils import load_wav
            
            ref = self.settings.get("cosyvoice_reference_path") or self.settings.get("qwen_reference_path")
            if isinstance(ref, str):
                ref = ref.strip(' \t\n\r"')
            if not ref or not Path(ref).exists():
                ref = str(EXE_BASE / "voice.mp3")
                
            if not Path(ref).exists():
                self.log("⚠ Файл референсного голоса не найден.")
                return False
                
            prompt_speech_16k = load_wav(ref, 16000)
            prompt_text = self.settings.get("cosyvoice_prompt_text", "")
            
            self.log("🎭 Генерация голоса через локальный CosyVoice...")
            with self.cosyvoice_lock:
                outputs = self.cosyvoice_model.inference_zero_shot(text, prompt_text, prompt_speech_16k)
                for output in outputs:
                    # output['tts_speech'] - это тензор формы [1, len]
                    torchaudio.save(str(path), output['tts_speech'], 22050)
                    break
            return True
        except Exception as e:
            self.log(f"❌ Ошибка генерации CosyVoice: {e}")
            self.log_exception("CosyVoice Generator")
            return False

    def _generate_cosyvoice_api(self, text, path):
        import urllib.request
        import urllib.parse
        import json
        
        api_url = self.settings.get("cosyvoice_api_url", "http://127.0.0.1:9880")
        url = f"{api_url}/tts" if not api_url.endswith("/tts") else api_url
        
        payload = {
            "text": text,
            "text_lang": "ru",
            "prompt_text": self.settings.get("cosyvoice_prompt_text", ""),
            "prompt_lang": "ru"
        }
        
        ref = self.settings.get("cosyvoice_reference_path") or self.settings.get("qwen_reference_path")
        if isinstance(ref, str):
            ref = ref.strip(' \t\n\r"')
        if ref and Path(ref).exists():
            payload["ref_audio_path"] = str(Path(ref).resolve())
            
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        
        try:
            self.log(f"🎭 Запрос генерации к CosyVoice API ({api_url})...")
            with urllib.request.urlopen(req, timeout=30) as response:
                with open(path, "wb") as f:
                    f.write(response.read())
            # Успешный ответ — помечаем сервер как подтверждённый
            self.cosyvoice_api_confirmed = True
            self.cosyvoice_ready = True
            return True
        except Exception as e:
            self.log(f"⚠ Ошибка CosyVoice API: {e}")
            return False

    def _load_qwen(self):
        if self.qwen_loading or self.qwen_ready: return
        self.qwen_loading = True
        self.log("⬇ Загрузка Qwen3-TTS (Voice Clone)...")
        
        def loader():
            try:
                import torch
                
                try:
                    from qwen_tts import Qwen3TTSModel
                except ImportError:
                    self.log("📦 Установка qwen-tts...")
                    subprocess.run([sys.executable, "-m", "pip", "install", "qwen-tts"], creationflags=0x08000000)
                    from qwen_tts import Qwen3TTSModel

                if torch.cuda.is_available():
                    torch.backends.cudnn.benchmark = True
                    torch.backends.cuda.matmul.allow_tf32 = True
                    torch.backends.cudnn.allow_tf32 = True

                # float16 отключён для Qwen3-TTS, так как он вызывает числовую нестабильность (NaN)
                # во время генерации (вызывая CUDA device-side assert в multinomial/TensorCompare).
                # Используем bfloat16 для RTX 30xx/40xx+ (SM >= 8.0) и float32 для старых карт (SM < 8.0) / CPU.
                if torch.cuda.is_available():
                    cap = torch.cuda.get_device_capability()
                    use_dtype = torch.bfloat16 if cap[0] >= 8 else torch.float32
                else:
                    use_dtype = torch.float32

                self.qwen_model = Qwen3TTSModel.from_pretrained(
                    "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
                    device_map="auto",
                    torch_dtype=use_dtype
                )
                if hasattr(self.qwen_model, "eval"):
                    self.qwen_model.eval()

                # torch.compile: ускоряет повторные вызовы через CUDA graphs
                try:
                    if torch.cuda.is_available() and hasattr(torch, 'compile'):
                        self.qwen_model = torch.compile(
                            self.qwen_model, mode="reduce-overhead"
                        )
                        self.log("⚡ torch.compile активирован (reduce-overhead)")
                except Exception as compile_err:
                    self.log(f"⚠ torch.compile недоступен: {compile_err}")

                # Cache voice if ref exists
                ref = self.settings.get("qwen_reference_path")
                if isinstance(ref, str):
                    ref = ref.strip(' \t\n\r"')
                if not ref or not Path(ref).exists():
                    ref = str(EXE_BASE / "voice.mp3")
                
                if Path(ref).exists():
                    self._cache_voice(ref)
                else:
                    self.log("⚠ Референсный голос (voice.mp3) не найден. Клонирование может не работать.")
                
                # CUDA warmup: прогреваем GPU ядра dummy-инференсом
                if torch.cuda.is_available():
                    try:
                        self.log("🔥 Прогрев GPU...")
                        with torch.inference_mode():
                            _dummy_ref = self.settings.get("qwen_reference_path") or ""
                            if isinstance(_dummy_ref, str):
                                _dummy_ref = _dummy_ref.strip(' \t\n\r"')
                            if not _dummy_ref or not Path(_dummy_ref).exists():
                                _dummy_ref = str(EXE_BASE / "voice.mp3")
                            if Path(_dummy_ref).exists() and self._qwen_voice_prompt:
                                self.qwen_model.generate_voice_clone(
                                    text="Тест.",
                                    language="Russian",
                                    voice_clone_prompt=self._qwen_voice_prompt,
                                )
                        torch.cuda.synchronize()
                        self.log("🔥 GPU прогрет!")
                    except Exception as warmup_err:
                        self.log(f"⚠ Ошибка прогрева GPU: {warmup_err}")

                self.qwen_ready = True
                self.log("✅ Qwen3-TTS готов!")
                threading.Thread(target=self._warm_tts_cache, daemon=True).start()
                self.speak("Голосовые системы синхронизированы.")
            except Exception as e:
                self.log(f"❌ Ошибка Qwen: {e}")
            finally:
                self.qwen_loading = False
        
        threading.Thread(target=loader, daemon=True).start()

    def _cache_voice(self, path):
        try:
            self.log("✨ Кэширование голоса (совместимый режим)...")
            self._qwen_voice_prompt = self.qwen_model.create_voice_clone_prompt(
                ref_audio=path,
                x_vector_only_mode=True
            )
            self._qwen_ref_path = path
        except Exception as e:
            self._log_once("qwen_cache_voice", f"⚠ Не удалось закэшировать голос Qwen: {e}")

    def _generate_qwen(self, text, path):
        if not self.qwen_ready or not self.qwen_model:
            return False
        try:
            import soundfile as sf
            import torch

            ref = self.settings.get("qwen_reference_path")
            if isinstance(ref, str):
                ref = ref.strip(' \t\n\r"')
            if not ref or not Path(ref).exists():
                ref = str(EXE_BASE / "voice.mp3")

            if Path(ref).exists():
                if self._qwen_ref_path != ref or self._qwen_voice_prompt is None:
                    self._cache_voice(ref)

            if not self._qwen_voice_prompt:
                self.log("⚠ Ошибка: voice_clone_prompt пуст. Проверьте наличие voice.mp3")
                return False

            with self.qwen_tts_lock:
                with torch.inference_mode():
                    wavs, sr = self.qwen_model.generate_voice_clone(
                        text=text,
                        language="Russian",
                        voice_clone_prompt=self._qwen_voice_prompt,
                    )
                    # Синхронизируем GPU чтобы данные были готовы до записи
                    if torch.cuda.is_available():
                        torch.cuda.synchronize()
            sf.write(path, wavs[0], sr)
            return True
        except Exception as e:
            self.log(f"⚠ Сбой генерации Qwen3-TTS: {e}")
            return False

    def _generate_edge(self, text, path):
        try:
            import edge_tts
            import asyncio
            
            # Настройка голоса (по умолчанию Dmitry, можно Svetlana)
            voice = self.settings.get("edge_tts_voice", "ru-RU-DmitryNeural")
            
            async def _save():
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(str(path))
                
            try:
                asyncio.run(_save())
            except RuntimeError:
                # В случае если event loop уже запущен в текущем потоке
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(_save())
                loop.close()
                
            return True
        except Exception as e:
            self.log(f"⚠ Сбой Edge TTS: {e}")
            return False

    def _load_qwen_llm(self):
        if self.qwen_llm_loading: return
        self.qwen_llm_loading = True
        
        def loader():
            try:
                import subprocess
                flags = 0x08000000 if os.name == 'nt' else 0
                self.log("🧠 Инициализация Qwen LLM...")
                
                # 1. Dependency Check
                try:
                    import llama_cpp
                    from llama_cpp import Llama
                except ImportError:
                    self.log("📦 Установка llama-cpp-python (CUDA/CPU)...")
                    subprocess.run([sys.executable, "-m", "pip", "install", "llama-cpp-python", "--prefer-binary"], creationflags=flags)
                    from llama_cpp import Llama

                try:
                    import huggingface_hub
                except ImportError:
                    self.log("📦 Установка huggingface-hub...")
                    subprocess.run([sys.executable, "-m", "pip", "install", "huggingface-hub"], creationflags=flags)

                # 2. Model Configuration
                # Priority 1: User's custom GGUF model path from settings
                custom_model_path = self.settings.get("local_llm_path")
                if isinstance(custom_model_path, str):
                    custom_model_path = custom_model_path.strip(' \t\n\r"')

                if custom_model_path and Path(custom_model_path).exists():
                    self.log(f"✅ Использование пользовательской модели ИИ: {custom_model_path}")
                    model_path = str(Path(custom_model_path).resolve())
                else:
                    filename = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
                    local_path = EXE_BASE / filename
                    if local_path.exists():
                        self.log(f"✅ Найдена локальная модель: {filename}")
                        model_path = str(local_path)
                    else:
                        # Try to find any other .gguf file in the current directory
                        gguf_files = [p for p in EXE_BASE.glob("*.gguf") if "dflash" not in p.name.lower()]
                        if gguf_files:
                            self.log(f"✅ Найдена альтернативная локальная модель: {gguf_files[0].name}")
                            model_path = str(gguf_files[0])
                        else:
                            model_name = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
                            self.log(f"🔍 Загрузка модели {filename} с HuggingFace...")
                            from huggingface_hub import hf_hub_download
                            model_path = hf_hub_download(repo_id=model_name, filename=filename, local_dir=str(EXE_BASE))
                
                # 3. Load Model
                def try_load(path):
                    self.log(f"🧠 Загрузка модели в память ({Path(path).name})...")
                    gpu_layers = self.settings.get("local_llm_gpu_layers", -1)
                    try:
                        return Llama(
                            model_path=path,
                            n_ctx=2048,
                            n_gpu_layers=gpu_layers, # Try user specified layer count
                            verbose=False
                        )
                    except Exception as gpu_e:
                        self.log(f"⚠ Сбой загрузки (слои {gpu_layers}): {gpu_e}. Пробую автоматический/CPU режим...")
                        try:
                            return Llama(
                                model_path=path,
                                n_ctx=2048,
                                n_gpu_layers=0, # Fallback to CPU
                                verbose=False
                            )
                        except Exception as cpu_e:
                            self.log(f"❌ Критическая ошибка при загрузке на CPU: {cpu_e}")
                            raise cpu_e

                try:
                    self.qwen_llm_model = try_load(model_path)
                except Exception as load_error:
                    default_filename = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
                    if Path(model_path).name != default_filename:
                        self.log(f"⚠ Модель {Path(model_path).name} не удалось загрузить. Возможно, архитектура не поддерживается (например, speculative draft).")
                        self.log(f"🔄 Попытка загрузить стандартную модель {default_filename}...")
                        
                        local_path = EXE_BASE / default_filename
                        if not local_path.exists():
                            model_name = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
                            self.log(f"🔍 Загрузка стандартной модели {default_filename} с HuggingFace...")
                            from huggingface_hub import hf_hub_download
                            model_path = hf_hub_download(repo_id=model_name, filename=default_filename, local_dir=str(EXE_BASE))
                        else:
                            model_path = str(local_path)
                        
                        self.qwen_llm_model = try_load(model_path)
                    else:
                        raise load_error
                
                self.log("✅ Qwen LLM готова!")
                self.speak("Локальный мозг подключен, сэр.")
                
            except Exception as e:
                self.log(f"❌ Ошибка Qwen LLM: {e}")
                self.qwen_llm_model = None
            finally:
                self.qwen_llm_loading = False
                
        threading.Thread(target=loader, daemon=True).start()

    def _visual_media_control(self):
        """Резервный метод управления медиа через поиск кнопок в системном оверлее Windows."""
        try:
            if not OCR_AVAILABLE: return
            # Даем оверлею время появиться (например, после нажатия горячей клавиши или изменения громкостти)
            time.sleep(0.5)
            
            p = CACHE_DIR / "media_check.png"
            pyautogui.screenshot(str(p))
            img = cv2.imread(str(p))
            if img is None: return
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            import pytesseract
            from pytesseract import Output
            
            # Ищем заголовок или название сервиса
            data = pytesseract.image_to_data(gray, lang='rus+eng', output_type=Output.DICT)
            target_keywords = ["youtube", "music", "spotify", "yandex", "playing", "сейчас", "воспроизводится"]
            
            n_boxes = len(data['text'])
            for i in range(n_boxes):
                if int(data['conf'][i]) > 50:
                    text = data['text'][i].lower()
                    if any(kw in text for kw in target_keywords):
                        # Нашли область управления медиа
                        tx = data['left'][i] + data['width'][i] // 2
                        ty = data['top'][i] + data['height'][i] // 2
                        
                        # В стандартном оверлее Windows кнопка плей/пауза обычно находится:
                        # - Либо чуть ниже заголовка (Win 10)
                        # - Либо в том же блоке справа/слева (Win 11 Quick Settings)
                        # На основе скриншота пользователя: кнопка Play ровно под текстом.
                        self.log(f"🎯 Найдено управление медиа '{text}', пробую кликнуть...")
                        
                        # Пытаемся кликнуть в области ниже текста
                        # В Win11 Quick Settings кнопка Play/Pause довольно крупная.
                        pyautogui.click(tx, ty + 60)
                        return
        except Exception as e:
            self.log(f"⚠ Ошибка визуального медиа-контроля: {e}")

    def _deep_sleep_monitor(self):
        while True:
            idle_time = time.time() - self.last_activity_time
            if idle_time > 300: # 5 minutes
                # Если модели включены в настройках — не выгружаем их неожиданно.
                keep_llama = bool(self.settings.get("use_llama"))
                keep_qwen = bool(self.settings.get("use_qwen_tts")) and bool(
                    self.settings.get("tts_keep_gpu_warm", True)
                )
                keep_cosyvoice = bool(self.settings.get("use_cosyvoice_tts")) and bool(
                    self.settings.get("tts_keep_gpu_warm", True)
                )

                should_unload_llama = (not keep_llama) and getattr(self, "llama_model", None) is not None
                should_unload_qwen = (not keep_qwen) and bool(self.qwen_model)
                should_unload_cosyvoice = (not keep_cosyvoice) and getattr(self, "cosyvoice_model", None) is not None

                if should_unload_llama or should_unload_qwen or should_unload_cosyvoice:
                    self.log("💤 Глубокий сон: выгрузка тяжелых моделей...")
                    if should_unload_llama:
                        self.llama_model = None
                    if should_unload_qwen:
                        self.qwen_model = None
                        self.qwen_ready = False
                        self._qwen_voice_prompt = None
                    if should_unload_cosyvoice:
                        self.cosyvoice_model = None
                        self.cosyvoice_ready = False
                    import gc
                    gc.collect()
            time.sleep(60)

# --- BRIDGE INSTANCE ---
# We will create this inside start() to ensure eel.init() is called first
jarvis = None

# --- EEL EXPORTS ---
@eel.expose
def start_listening():
    if jarvis:
        jarvis.is_listening = True
        jarvis.log("Система активна.")
        return True
    return False

@eel.expose
def stop_listening():
    if jarvis:
        jarvis.is_listening = False
        jarvis.log("Система в режиме ожидания.")
        return True
    return False

@eel.expose
def process(text):
    if jarvis:
        jarvis.process_command(text)
        return True
    return False

@eel.expose
def get_status():
    if not jarvis: return {"is_listening": False, "is_speaking": False, "ai": "Offline"}
    
    # Режим распознавания (STT)
    stt = "Vosk" if jarvis.settings.get("use_vosk") else "Google"
    
    # Мозг (LLM)
    if jarvis.settings.get("use_online_ai", True):
        llm = "Yandex"
    elif jarvis.settings.get("use_qwen_llm"):
        llm = "Qwen"
    else:
        llm = ""
    
    # Синтез (TTS)
    if jarvis.settings.get("use_qwen_tts"):
        tts = "Qwen-TTS"
    elif jarvis.settings.get("use_cosyvoice_tts"):
        tts = "CosyVoice"
    else:
        tts = ""
    
    # Собираем строку статуса
    ai_parts = [stt]
    if llm: ai_parts.append(llm)
    if tts: ai_parts.append(tts)
    ai_status = " + ".join(ai_parts)
    
    return {
        "is_listening": jarvis.is_listening,
        "is_speaking": jarvis.is_speaking,
        "ai": ai_status
    }

@eel.expose
def get_settings():
    return jarvis.settings if jarvis else {}

@eel.expose
def update_settings(new_settings):
    if not jarvis: return False
    try:
        old_llama = jarvis.settings.get("use_llama")
        old_qwen = jarvis.settings.get("use_qwen_tts")
        old_cosyvoice = jarvis.settings.get("use_cosyvoice_tts")
        old_power_saving = jarvis.settings.get("power_saving_enabled")
        old_performance_mode = jarvis.settings.get("performance_mode")
        jarvis.settings.update(new_settings)
        with open(EXE_BASE / "jarvis_settings.json", "w", encoding='utf-8') as f:
            json.dump(jarvis.settings, f, ensure_ascii=False, indent=2)

        # Trigger loading if toggled ON
        if jarvis.settings.get("use_llama") and not old_llama:
            jarvis._load_llama()
        if jarvis.settings.get("use_qwen_tts") and not old_qwen:
            jarvis._load_qwen()
        if jarvis.settings.get("use_cosyvoice_tts") and not old_cosyvoice:
            jarvis._load_cosyvoice()


        # Handle power saving mode
        if jarvis.settings.get("power_saving_enabled") and not old_power_saving:
            # Enable power saving mode
            jarvis.enter_power_saving_mode()
        elif not jarvis.settings.get("power_saving_enabled") and old_power_saving:
            # Disable power saving mode
            jarvis.exit_power_saving_mode()

        # Handle performance mode changes
        if jarvis.settings.get("performance_mode") != old_performance_mode:
            jarvis.adjust_performance_mode()

        # Handle smart home settings changes
        if (jarvis.settings.get("smart_home_api_url") != jarvis.settings.get("smart_home_api_url", "") or
            jarvis.settings.get("smart_home_access_token") != jarvis.settings.get("smart_home_access_token", "")):
            # Reinitialize smart home controller with new settings
            smart_home_config = {
                "api_url": jarvis.settings.get("smart_home_api_url", ""),
                "access_token": jarvis.settings.get("smart_home_access_token", "")
            }
            jarvis.smart_home.initialize(smart_home_config)

        jarvis.log("Настройки синхронизированы.")
        return True
    except: return False

@eel.expose
def add_custom_command(keyword, action):
    if not jarvis: return False
    try:
        jarvis.cmds[keyword.lower()] = {"action": action, "action_type": "program"}
        with open(EXE_BASE / "jarvis_cmds.json", "w", encoding='utf-8') as f:
            json.dump(jarvis.cmds, f, ensure_ascii=False, indent=2)
        jarvis.log(f"Добавлена команда: {keyword}")
        return True
    except Exception as e:
        try:
            jarvis.log(f"⚠ Ошибка сохранения команды '{keyword}': {e}")
        except Exception:
            pass
        return False

@eel.expose
def get_commands():
    """Возвращает все пользовательские команды для отображения в UI."""
    if not jarvis:
        return {}
    return jarvis.cmds

@eel.expose
def set_autostart(enabled):
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "JARVIS_ULTIMATE"
        app_path = f'"{sys.executable}" "{Path(__file__).resolve()}"'
        
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_path)
            jarvis.log("Автозапуск включен.")
        else:
            try: winreg.DeleteValue(key, app_name)
            except: pass
            jarvis.log("Автозапуск выключен.")
        winreg.CloseKey(key)
        
        jarvis.settings["autostart"] = enabled
        with open(EXE_BASE / "jarvis_settings.json", "w", encoding='utf-8') as f:
            json.dump(jarvis.settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        jarvis.log(f"Ошибка автозапуска: {e}")
        return False

# --- START APP ---
def cleanup_zombies():
    """Мягкая очистка — НЕ убиваем Chrome (Eel его использует для UI)."""
    # Убираем агрессивное убийство процессов — оно вызывало проблемы
    pass

def _find_browser_mode():
    """Определяет лучший браузер для app-режима (отдельное окно без адресной строки)."""
    
    # Проверяем Chrome
    chrome_paths = [
        os.environ.get('PROGRAMFILES', '') + r'\Google\Chrome\Application\chrome.exe',
        os.environ.get('PROGRAMFILES(X86)', '') + r'\Google\Chrome\Application\chrome.exe',
        os.environ.get('LOCALAPPDATA', '') + r'\Google\Chrome\Application\chrome.exe',
    ]
    for p in chrome_paths:
        if p and os.path.exists(p):
            return 'chrome'
    
    # Проверяем Edge (есть на всех Windows 10/11)
    edge_paths = [
        os.environ.get('PROGRAMFILES', '') + r'\Microsoft\Edge\Application\msedge.exe',
        os.environ.get('PROGRAMFILES(X86)', '') + r'\Microsoft\Edge\Application\msedge.exe',
    ]
    for p in edge_paths:
        if p and os.path.exists(p):
            return 'edge'
    
    # Fallback — пусть Eel сам попробует
    return 'chrome'

def find_guaranteed_port():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', 0)) # Force explicit IPv4 loopback
        port = s.getsockname()[1]
        s.close()
        time.sleep(0.3)
        return port
    except:
        return 8000 + random.randint(1, 1000)

def start_models_with_delay():
    time.sleep(6)
    try:
        if jarvis:
            if jarvis.settings.get("use_qwen_llm"): jarvis._load_qwen_llm()
            if jarvis.settings.get("use_qwen_tts"): jarvis._load_qwen()
            if jarvis.settings.get("use_cosyvoice_tts"): jarvis._load_cosyvoice()
            if jarvis.settings.get("use_qwen_cli"):
                jarvis.log("💻 Прогрев Qwen CLI (локальный запуск)...")
                try:
                    # Выполняем тестовый запрос вместо простой проверки версии
                    # Это принудительно загрузит модель в память
                    res = subprocess.run(["qwen", "привет"], shell=True, capture_output=True, text=True, timeout=40)
                    if res.returncode == 0:
                        jarvis.log("✅ Qwen CLI прогрет и готов к работе.")
                    else:
                        raise Exception(f"Код возврата: {res.returncode}")
                except Exception as e:
                    jarvis.log(f"❌Ошибка запуска Qwen CLI: {e}")
                    jarvis.speak("Сэр, локальный мозг Ку вэн не отвечает. Проверьте консоль.")
    except Exception as e:
        try:
            if jarvis:
                jarvis._log_once("start_models_with_delay", f"⚠ Ошибка фоновой загрузки моделей: {e}")
        except Exception:
            pass

def start():
    global jarvis
    import sys
    
    # Защита от pythonw.exe (двойной клик по .py без консоли)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')
    
    # Force immediate output + UTF-8 для эмодзи
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
    
    print("\n" + "="*40)
    print("[SYSTEM] Инициализация протокола IPv4 FORCE")
    print("="*40)
    sys.stdout.flush()

    # 1. Aggressive Cleanup
    print("[1/5] Очистка старых процессов...")
    cleanup_zombies()

    # 2. Path & Eel Init
    # web_dir already defined globally as WEB_DIR
    web_dir = WEB_DIR
    os.chdir(EXE_BASE) # User files and models should be relative to EXE
    
    if not web_dir.exists():
        print(f"[FATAL] Ошибка: Папка 'web' не найдена по пути {web_dir}")
        input("Нажмите Enter для выхода...")
        return

    eel.init(str(web_dir))

    # 3. JARVIS Core
    print("[2/5] Загрузка ядра JARVIS...")
    sys.stdout.flush()
    try:
        jarvis = JarvisEel()
    except Exception as e:
        import traceback
        print(f"[ERROR] Крах ядра:\n{traceback.format_exc()}")
        input("Нажмите Enter...")
        return
    
    # 4. Background Loaders
    threading.Thread(target=start_models_with_delay, daemon=True).start()
    
    # 5. Connect UI (Explicit IPv4)
    port = find_guaranteed_port()
    host = '127.0.0.1' # Forcing IPv4 loopback
    
    print(f"[3/5] UI готов к запуску на {host}:{port}")
    print(f"[4/5] Если браузер не открылся, перейдите вручную: http://{host}:{port}")
    sys.stdout.flush()
    
    try:
        print("[5/5] Запуск интерфейса...")
        sys.stdout.flush()
        
        browser_url = f"http://{host}:{port}"
        
        # Определяем доступный браузер для app-режима (отдельное окно)
        browser_mode = _find_browser_mode()
        print(f"[INFO] Режим браузера: {browser_mode}")
        
        eel.start('index.html',
                  mode=browser_mode,
                  host=host,
                  port=port,
                  size=(600, 850),
                  block=True,
                  shutdown_delay=9999)
                  
        # If eel.start returns unexpectedly, we keep the process alive for logs
        print("\n[WARN] Интерфейс Eel вернул управление.")
        print(f"[INFO] Вы можете открыть интерфейс вручную: {browser_url}")
        while True:
            time.sleep(1)
                
    except BaseException as e:
        import traceback
        print(f"\n[КРИТИЧЕСКИЙ СБОЙ ПРИ ЗАПУСКЕ]\n{traceback.format_exc()}")
        sys.stdout.flush()
        print("\nПрограмма НЕ закрывается автоматически, чтобы вы могли прочитать ошибку.")
        while True:
            time.sleep(1)

if __name__ == "__main__":
    import ctypes
    import sys
    import time
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "JarvisEelSingleInstanceMutex")
    if ctypes.windll.kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS
        print("Jarvis уже запущен! Пожалуйста, закройте предыдущую копию.")
        time.sleep(3)
        sys.exit(0)

    try:
        start()
    except BaseException as e:
        import traceback
        print(f"\n[ФАТАЛЬНАЯ ОШИБКА]\n{traceback.format_exc()}")
        input("\nНажмите Enter для выхода...")
