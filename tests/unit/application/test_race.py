from rental_shop.application.race import Race

from .fakes import InMemoryShop


def test_exactly_one_of_twenty_contenders_wins_and_the_rest_are_refused():
    shop = InMemoryShop()
    tally = Race(shop.open, sleep=lambda _: None, contenders=20).run_round("1")
    assert (tally.successes, tally.refused, tally.failed) == (1, 19, 0)
    assert tally.is_correct
    assert len(shop.rentals) == 1


def test_every_round_uses_a_fresh_item_so_rounds_do_not_affect_each_other():
    shop = InMemoryShop()
    race = Race(shop.open, sleep=lambda _: None, contenders=5)
    assert race.run_round("1").is_correct
    assert race.run_round("2").is_correct
    assert len(shop.items) == 2
    assert len(shop.rentals) == 2


def test_deadlock_victims_are_retried_and_counted_and_still_end_up_refused():
    shop = InMemoryShop(deadlocks_to_raise=3)
    tally = Race(shop.open, sleep=lambda _: None, contenders=6).run_round("1")
    assert tally.is_correct
    assert tally.deadlock_retries == 3


def test_a_contender_that_loses_every_retry_to_deadlocks_is_counted_apart_from_other_failures():
    shop = InMemoryShop(deadlocks_to_raise=10_000)
    tally = Race(shop.open, sleep=lambda _: None, contenders=3).run_round("1")
    assert (tally.successes, tally.deadlocked, tally.failed) == (0, 3, 0)
    assert not tally.one_winner


def test_a_contender_that_fails_for_another_reason_is_counted_and_the_round_is_not_correct():
    class Broken(InMemoryShop):
        def book(self, item_id, customer_id, period):
            raise RuntimeError("connection lost")

    shop = Broken()
    tally = Race(shop.open, sleep=lambda _: None, contenders=4).run_round("1")
    assert tally.failed == 4
    assert not tally.is_correct
