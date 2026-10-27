"""Use case: the five questions of the rental shop, each as one call, for the report program."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..domain.errors import RentalShopError
from ..domain.model import Customer, Item, MonthlyRevenue, Rental, ReturnDue
from ..domain.period import RentalPeriod
from .ports import Clock, RentalQueries


class UnknownCustomerNameError(RentalShopError):
    """No single customer has this name."""

    def __init__(self, name: str) -> None:
        super().__init__(f"no customer named {name!r}")


@dataclass(frozen=True, slots=True)
class ShopReport:
    """The answers to the five questions for one set of inputs."""

    free_items: list[Item]
    customer: Customer
    history: list[Rental]
    returns_today: list[ReturnDue]
    today: date
    revenue: list[MonthlyRevenue]
    never_rented: list[Item]


@dataclass(frozen=True, slots=True)
class ShopQuestions:
    """Asks the repository the five questions of lesson step 1."""

    queries: RentalQueries
    clock: Clock

    def report(self, weekend: RentalPeriod, customer_name: str, today: date | None = None) -> ShopReport:
        """Answer all five. `today` defaults to the injected clock's date."""
        customer = self.queries.find_customer(customer_name)
        if customer is None:
            raise UnknownCustomerNameError(customer_name)
        day = today or self.clock.today()
        return ShopReport(
            free_items=self.queries.free_items(weekend),
            customer=customer,
            history=self.queries.history(customer.customer_id),
            returns_today=self.queries.returns_on(day),
            today=day,
            revenue=self.queries.revenue_by_item_and_month(),
            never_rented=self.queries.never_rented(),
        )
