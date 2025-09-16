import attrs


@attrs.define(frozen=True)
class CurrentUserInfo:
    """Current user information for controllers - avoids cross-domain dependencies"""

    user_id: int
    role: str  # 'buyer' or 'seller'

    def is_buyer(self) -> bool:
        return self.role == 'buyer'

    def is_seller(self) -> bool:
        return self.role == 'seller'
