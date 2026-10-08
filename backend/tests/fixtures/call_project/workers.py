from helpers import local_helper


def local_target() -> None:
    pass


def local_caller() -> None:
    local_target()


class Repository:
    def save(self) -> None:
        self.validate()

    def validate(self) -> None:
        pass

    def run(self) -> None:
        local_helper()
        self.save()

    def missing(self) -> None:
        missing_target()
        self.not_found()

    def with_unknown_receiver(self, obj) -> None:
        obj.save()


class Base:
    def inherited(self) -> None:
        pass


class Child(Base):
    def run(self) -> None:
        self.inherited()


class CycleA(CycleB):
    def run(self) -> None:
        self.absent_from_cycle()


class CycleB(CycleA):
    pass


class Root:
    def deep_method(self) -> None:
        pass


class Level1(Root):
    pass


class Level2(Level1):
    pass


class Level3(Level2):
    pass


class Level4(Level3):
    pass


class Level5(Level4):
    pass


class Level6(Level5):
    def run(self) -> None:
        self.deep_method()


def make_repository() -> None:
    repository = Repository()
    repository.save()