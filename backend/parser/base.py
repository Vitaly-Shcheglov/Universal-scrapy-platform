import requests
import time
import hashlib
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from django.conf import settings


class BaseExtractor(ABC):
    """Базовый класс для всех экстракторов"""

    def __init__(self, source):
        self.source = source
        self.session = requests.Session()
        self.ua = UserAgent


class BaseExtractor(ABC):
    """Базовый класс для всех экстракторов"""

    def __init__(self, source):
        self.source = source
        self.session = requests.Session()
        self.ua = UserAgent()
        self.setup_session()

    def setup_session(self):
        """Настройка HTTP сессии"""
        headers = {
            'User-Agent': settings.PARSER_SETTINGS.get('USER_AGENT', self.ua.random),
            'Accept': 'text/html,application/json,*/*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }

        # Добавляем кастомные заголовки из источника
        if self.source.headers:
            headers.update(self.source.headers)

        self.session.headers.update(headers)

    def fetch(self, url: str, method: str = 'GET', **kwargs) -> requests.Response:
        """Выполнить HTTP запрос с повторами"""
        timeout = settings.PARSER_SETTINGS.get('TIMEOUT', 30)
        retry_count = settings.PARSER_SETTINGS.get('RETRY_COUNT', 3)
        delay = settings.PARSER_SETTINGS.get('DELAY', 1)

        for attempt in range(retry_count):
            try:
                time.sleep(delay)  # Задержка между запросами

                response = self.session.request(
                    method=method,
                    url=url,
                    timeout=timeout,
                    **kwargs
                )
                response.raise_for_status()
                return response

            except requests.exceptions.RequestException as e:
                if attempt == retry_count - 1:
                    raise
                time.sleep(delay * (attempt + 1))

        raise Exception(f"Не удалось выполнить запрос после {retry_count} попыток")

    @abstractmethod
    def extract_list(self, **kwargs) -> List[Dict[str, Any]]:
        """Извлечь список товаров"""
        pass

    @abstractmethod
    def extract_detail(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Извлечь детальную информацию о товаре"""
        pass

    def normalize_price(self, price_str: str) -> Optional[float]:
        """Нормализовать цену"""
        if not price_str:
            return None

        # Убираем все кроме цифр, точки и запятой
        price_str = ''.join(c for c in str(price_str) if c.isdigit() or c in '.,')
        price_str = price_str.replace(',', '.')

        try:
            return float(price_str)
        except (ValueError, AttributeError):
            return None

    def calculate_hash(self, data: Dict[str, Any]) -> str:
        """Вычислить хеш данных товара"""
        # Берем только важные поля для хеша
        hash_fields = ['name', 'price', 'availability', 'description']
        hash_data = {k: v for k, v in data.items() if k in hash_fields}

        json_str = json.dumps(hash_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def clean_text(self, text: str) -> str:
        """Очистить текст от лишних символов"""
        if not text:
            return ''
        return ' '.join(text.split()).strip()


class HTMLExtractor(BaseExtractor):
    """Экстрактор для HTML страниц"""

    def parse_html(self, html: str) -> BeautifulSoup:
        """Парсить HTML"""
        return BeautifulSoup(html, 'lxml')

    def extract_list(self, url: str = None, **kwargs) -> List[Dict[str, Any]]:
        """Извлечь список товаров из HTML"""
        url = url or self.source.base_url
        response = self.fetch(url)
        soup = self.parse_html(response.text)

        items = []
        config = self.source.config or {}

        # Селектор для списка товаров
        list_selector = config.get('list_selector', '.product-item')
        product_elements = soup.select(list_selector)

        for element in product_elements:
            try:
                item = self.extract_item_from_element(element, config)
                if item:
                    items.append(item)
            except Exception as e:
                print(f"Ошибка при извлечении товара: {e}")
                continue

        return items

    def extract_item_from_element(self, element, config: Dict) -> Optional[Dict[str, Any]]:
        """Извлечь данные товара из HTML элемента"""
        try:
            # Селекторы из конфига
            selectors = config.get('selectors', {})

            name_elem = element.select_one(selectors.get('name', '.product-name'))
            price_elem = element.select_one(selectors.get('price', '.product-price'))
            url_elem = element.select_one(selectors.get('url', 'a'))
            image_elem = element.select_one(selectors.get('image', 'img'))

            if not name_elem or not price_elem:
                return None

            item = {
                'name': self.clean_text(name_elem.get_text()),
                'price': self.normalize_price(price_elem.get_text()),
                'url': url_elem.get('href') if url_elem else '',
                'image_url': image_elem.get('src') if image_elem else '',
            }

            # Дополнительные поля
            if 'article' in selectors:
                article_elem = element.select_one(selectors['article'])
                if article_elem:
                    item['article'] = self.clean_text(article_elem.get_text())

            if 'brand' in selectors:
                brand_elem = element.select_one(selectors['brand'])
                if brand_elem:
                    item['brand'] = self.clean_text(brand_elem.get_text())

            return item

        except Exception as e:
            print(f"Ошибка извлечения элемента: {e}")
            return None

    def extract_detail(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Извлечь детальную информацию"""
        url = item_data.get('url')
        if not url:
            return item_data

        try:
            response = self.fetch(url)
            soup = self.parse_html(response.text)

            config = self.source.config or {}
            detail_selectors = config.get('detail_selectors', {})

            # Описание
            if 'description' in detail_selectors:
                desc_elem = soup.select_one(detail_selectors['description'])
                if desc_elem:
                    item_data['description'] = self.clean_text(desc_elem.get_text())

            # Характеристики
            if 'specifications' in detail_selectors:
                specs = {}
                spec_elements = soup.select(detail_selectors['specifications'])
                for spec_elem in spec_elements:
                    key_elem = spec_elem.select_one('.spec-key')
                    value_elem = spec_elem.select_one('.spec-value')
                    if key_elem and value_elem:
                        specs[self.clean_text(key_elem.get_text())] = self.clean_text(value_elem.get_text())
                item_data['specifications'] = specs

            # Дополнительные изображения
            if 'images' in detail_selectors:
                images = []
                img_elements = soup.select(detail_selectors['images'])
                for img_elem in img_elements:
                    img_url = img_elem.get('src') or img_elem.get('data-src')
                    if img_url:
                        images.append(img_url)
                item_data['images'] = images

        except Exception as e:
            print(f"Ошибка при получении деталей: {e}")

        return item_data


class APIExtractor(BaseExtractor):
    """Экстрактор для API"""

    def extract_list(self, endpoint: str = None, params: Dict = None, **kwargs) -> List[Dict[str, Any]]:
        """Извлечь список товаров из API"""
        url = endpoint or self.source.base_url

        response = self.fetch(url, params=params)
        data = response.json()

        config = self.source.config or {}
        items_path = config.get('items_path', 'items')

        # Извлекаем список товаров по пути
        items = self.get_nested_value(data, items_path)

        if not isinstance(items, list):
            return []

        result = []
        for item in items:
            try:
                normalized = self.normalize_api_item(item, config)
                if normalized:
                    result.append(normalized)
            except Exception as e:
                print(f"Ошибка нормализации: {e}")
                continue

        return result

    def normalize_api_item(self, item: Dict, config: Dict) -> Optional[Dict[str, Any]]:
        """Нормализовать данные из API"""
        mapping = config.get('field_mapping', {})

        normalized = {}

        # Маппинг полей
        for our_field, their_field in mapping.items():
            value = self.get_nested_value(item, their_field)
            if value is not None:
                normalized[our_field] = value

        # Нормализация цены
        if 'price' in normalized:
            normalized['price'] = self.normalize_price(normalized['price'])

        return normalized if normalized else None

    def get_nested_value(self, data: Dict, path: str) -> Any:
        """Получить значение по вложенному пути (например: 'data.items.0.name')"""
        keys = path.split('.')
        value = data

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            elif isinstance(value, list) and key.isdigit():
                try:
                    value = value[int(key)]
                except (IndexError, ValueError):
                    return None
            else:
                return None

        return value

    def extract_detail(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Извлечь детальную информацию из API"""
        # Если API возвращает полные данные сразу
        return item_data


class CSVExtractor(BaseExtractor):
    """Экстрактор для CSV файлов"""

    def extract_list(self, file_path: str = None, **kwargs) -> List[Dict[str, Any]]:
        """Извлечь список товаров из CSV"""
        import csv

        items = []
        config = self.source.config or {}
        encoding = config.get('encoding', 'utf-8')
        delimiter = config.get('delimiter', ',')

        with open(file_path, 'r', encoding=encoding) as f:
            reader = csv.DictReader(f, delimiter=delimiter)

            for row in reader:
                try:
                    item = self.normalize_csv_row(row, config)
                    if item:
                        items.append(item)
                except Exception as e:
                    print(f"Ошибка обработки строки: {e}")
                    continue

        return items

    def normalize_csv_row(self, row: Dict, config: Dict) -> Optional[Dict[str, Any]]:
        """Нормализовать строку CSV"""
        mapping = config.get('field_mapping', {})

        normalized = {}

        for our_field, csv_column in mapping.items():
            if csv_column in row:
                value = row[csv_column].strip()

                if our_field == 'price':
                    value = self.normalize_price(value)

                normalized[our_field] = value

        return normalized if normalized else None

    def extract_detail(self, item_data: Dict[str, Any) -> Dict[str, Any]:
        """CSV обычно содержит все данные"""

    return item_data
