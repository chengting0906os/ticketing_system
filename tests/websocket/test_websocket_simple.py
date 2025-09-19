import pytest

from src.shared.service.jwt_auth_service import CustomJWTStrategy, get_jwt_strategy
from src.user.domain.user_model import User, UserRole


class TestWebSocketJWT:
    @pytest.mark.asyncio
    async def test_jwt_token_generation(self):
        """Test JWT token generation with user role"""
        user = User(
            id=123,
            email='test@example.com',
            name='Test User',
            role=UserRole.BUYER,
            hashed_password='test_hash',
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )

        jwt_strategy = get_jwt_strategy()

        # Generate token
        token = await jwt_strategy.write_token(user)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 50

    @pytest.mark.asyncio
    async def test_jwt_token_decode(self):
        """Test JWT token decode with role extraction"""
        user = User(
            id=456,
            email='seller@example.com',
            name='Seller User',
            role=UserRole.SELLER,
            hashed_password='test_hash',
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )

        jwt_strategy = get_jwt_strategy()

        token = await jwt_strategy.write_token(user)
        from src.shared.service.jwt_auth_service import CustomJWTStrategy

        if isinstance(jwt_strategy, CustomJWTStrategy):
            user_data = jwt_strategy.decode_token_simple(token)
        else:
            user_data = None

        assert user_data is not None
        assert user_data['user_id'] == 456
        assert user_data['role'] == 'seller'
        assert user_data['email'] == 'seller@example.com'

    @pytest.mark.asyncio
    async def test_websocket_user_creation(self):
        user = User(
            id=789,
            email='buyer@example.com',
            name='Buyer User',
            role=UserRole.BUYER,
            hashed_password='test_hash',
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )

        jwt_strategy = get_jwt_strategy()
        token = await jwt_strategy.write_token(user)

        if isinstance(jwt_strategy, CustomJWTStrategy):
            user_data = jwt_strategy.decode_token_simple(token)
        else:
            user_data = None

        ws_user = None
        if user_data:
            ws_user = User(
                id=user_data['user_id'],
                email=user_data.get('email', ''),
                name='WebSocket User',
                role=UserRole(user_data['role']),
                hashed_password='',
                is_active=True,
                is_superuser=False,
                is_verified=True,
            )

            assert ws_user.id == 789
            assert ws_user.role == UserRole.BUYER
            assert ws_user.email == 'buyer@example.com'
