import pytest
from django.db import IntegrityError

from city.models import City


@pytest.mark.django_db
def test_city_has_order_field():
    city = City.objects.create(order=1)
    assert hasattr(city, "order")
    assert city.order == 1


@pytest.mark.django_db
def test_cities_ordered_by_order_field():
    City.objects.create(order=3)
    City.objects.create(order=1)
    City.objects.create(order=2)

    orders = list(City.objects.values_list("order", flat=True))
    assert orders == [1, 2, 3]


@pytest.mark.django_db
def test_city_order_unique_constraint():
    City.objects.create(order=5)
    with pytest.raises(IntegrityError):
        City.objects.create(order=5)
