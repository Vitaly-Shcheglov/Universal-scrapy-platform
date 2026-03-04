from typing import List, Dict, Any, Optional, Type, TypeVar

from .extractors import (
    HTMLExtractor, APIExtractor, CSVExtractor,
    WildberriesExtractor, OzonExtractor, ExampleShopExtractor
)

TExtractor = TypeVar('TExtractor', bound='BaseExtractor')


class ExampleShopExtractor(HTMLExtractor):
    """Пример экстрактора для конкретного магазина"""

    def extract_list(self, **kwargs) -> list:
        """Кастомная логика извлечения списка"""
        items = []
        page = 1
        max_pages = kwargs.get('max_pages', 10)

        while page <= max_pages:
            url = f"{self.source.base_url}/catalog?page={page}"

            try:
                response = self.fetch(url)
                soup = self.parse_html(response.text)

                products = soup.select('.product-card')

                if not products:
                    break

                for product in products:
                    item = self.extract_product_card(product)
                    if item:
                        items.append(item)

                page += 1

            except Exception as e:
                print(f"Ошибка на странице {page}: {e}")
                break

        return items

    def extract_product_card(self, element):
        """Извлечь данные из карточки товара"""
        try:
            name = element.select_one('h3.product-name')
            price = element.select_one('span.price')
            old_price = element.select_one('span.old-price')
            link = element.select_one('a.product-link')
            image = element.select_one('img.product-image')
            article = element.select_one('span.article')
            availability = element.select_one('span.availability')

            return {
                'external_id': article.get_text().strip() if article else '',
                'name': name.get_text().strip() if name else '',
                'article': article.get_text().strip() if article else '',
                'price': self.normalize_price(price.get_text()) if price else 0,
                'old_price': self.normalize_price(old_price.get_text()) if old_price else None,
                'url': self.source.base_url + link.get('href') if link else '',
                'image_url': image.get('src') if image else '',
                'availability': self.parse_availability(availability.get_text() if availability else ''),
            }
        except Exception as e:
            print(f"Ошибка извлечения карточки: {e}")
            return None

    def parse_availability(self, text: str) -> str:
        """Парсинг статуса наличия"""
        text = text.lower()

        if 'в наличии' in text or 'есть' in text:
            return 'in_stock'
        elif 'нет в наличии' in text or 'отсутствует' in text:
            return 'out_of_stock'
        elif 'под заказ' in text or 'предзаказ' in text:
            return 'pre_order'
        else:
            return 'in_stock'  # По умолчанию


class WildberriesExtractor(APIExtractor):
    """Экстрактор для Wildberries API"""

    def extract_list(self, category_id: str = None, **kwargs) -> list:
        """Извлечение товаров через API Wildberries"""
        items = []
        page = 1

        while True:
            url = f"https://catalog.wb.ru/catalog/{category_id}/catalog"
            params = {
                'appType': 1,
                'curr': 'rub',
                'dest': -1257786,
                'page': page,
                'sort': 'popular',
                'spp': 0
            }

            try:
                response = self.fetch(url, params=params)
                data = response.json()

                products = data.get('data', {}).get('products', [])

                if not products:
                    break

                for product in products:
                    item = self.normalize_wb_product(product)
                    if item:
                        items.append(item)

                page += 1

            except Exception as e:
                print(f"Ошибка WB API: {e}")
                break

        return items

    def normalize_wb_product(self, product: dict) -> dict:
        """Нормализация данных Wildberries"""
        try:
            price = product.get('salePriceU', 0) / 100

            return {
                'external_id': str(product.get('id', '')),
                'name': product.get('name', ''),
                'article': str(product.get('id', '')),
                'brand': product.get('brand', ''),
                'price': price,
                'rating': product.get('rating', 0),
                'reviews_count': product.get('feedbacks', 0),
                'url': f"https://www.wildberries.ru/catalog/{product.get('id')}/detail.aspx",
                'image_url': self.get_wb_image_url(product.get('id')),
                'availability': 'in_stock',
            }
        except Exception as e:
            print(f"Ошибка нормализации WB: {e}")
            return None

    def get_wb_image_url(self, product_id: int) -> str:
        """Получить URL изображения WB"""
        vol = product_id // 100000
        part = product_id // 1000
        return f"https://basket-{vol:02d}.wb.ru/vol{vol}/part{part}/{product_id}/images/big/1.jpg"


class OzonExtractor(APIExtractor):
    """Экстрактор для Ozon (требует API ключ)"""

    def __init__(self, source):
        super().__init__(source)
        api_key = source.config.get('api_key')
        if api_key:
            self.session.headers['Api-Key'] = api_key

    def extract_list(self, **kwargs) -> list:
        """Извлечение через Ozon API"""
        url = "https://api-seller.ozon.ru/v2/product/list"

        payload = {
            "filter": {
                "visibility": "ALL"
            },
            "limit": 100,
            "last_id": ""
        }

        items = []

        try:
            response = self.fetch(url, method='POST', json=payload)
            data = response.json()

            for product in data.get('result', {}).get('items', []):
                item = self.normalize_ozon_product(product)
                if item:
                    items.append(item)

        except Exception as e:
            print(f"Ошибка Ozon API: {e}")

        return items

    def normalize_ozon_product(self, product: dict) -> dict:
        """Нормализация данных Ozon"""
        return {
            'external_id': str(product.get('product_id', '')),
            'name': product.get('name', ''),
            'article': product.get('offer_id', ''),
            'price': float(product.get('price', 0)),
            'availability': 'in_stock' if product.get('stocks', 0) > 0 else 'out_of_stock',
            'stock_quantity': product.get('stocks', 0),
        }


def get_extractor(source) -> TExtractor:
    """Фабрика экстракторов"""
    extractors: dict[str, Type[HTMLExtractor]] = {
        'html': HTMLExtractor,
        'api': APIExtractor,
        'csv': CSVExtractor,
        'xlsx': CSVExtractor,
        'json': APIExtractor,
    }

    # Можно добавить кастомные экстракторы по имени источника
    custom_extractors: dict[str, Type['BaseExtractor']] = {
        'wildberries': WildberriesExtractor,
        'ozon': OzonExtractor,
        'example_shop': ExampleShopExtractor,
    }

    source_name = source.name.lower()

    if source_name in custom_extractors:
        return custom_extractors[source_name](source)

    extractor_class: Type[HTMLExtractor] = extractors.get(source.source_type, HTMLExtractor)
    return extractor_class(source)
