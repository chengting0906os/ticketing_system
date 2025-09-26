#!/bin/bash

# 啟動分離的消費者
# 每個消費者負責單一職責

echo "🚀 啟動分離的消費者架構..."

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 檢查 Kafka 是否運行
echo -e "${YELLOW}檢查 Kafka 服務...${NC}"
if ! nc -z localhost 9092 2>/dev/null; then
    echo -e "${RED}❌ Kafka 服務未運行，請先啟動 Kafka${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Kafka 服務正常${NC}"

# 清理函數
cleanup() {
    echo -e "\n${YELLOW}⚠️ 收到中斷信號，停止所有消費者...${NC}"
    kill $(jobs -p) 2>/dev/null
    wait
    echo -e "${GREEN}✅ 所有消費者已停止${NC}"
    exit 0
}

# 設置信號處理
trap cleanup SIGINT SIGTERM

# 啟動票務請求消費者
echo -e "\n${BLUE}🎫 啟動票務請求消費者 (處理 BookingCreated 事件)...${NC}"
uv run python -m src.event_ticketing.infra.ticketing_request_consumer &
TICKETING_PID=$!
echo -e "${GREEN}   PID: $TICKETING_PID${NC}"

# 等待一秒讓第一個消費者啟動
sleep 1

# 啟動訂單回應消費者
echo -e "\n${BLUE}📚 啟動訂單回應消費者 (處理 TicketsReserved/Failed 事件)...${NC}"
uv run python -m src.booking.infra.booking_response_consumer &
BOOKING_PID=$!
echo -e "${GREEN}   PID: $BOOKING_PID${NC}"

# 顯示架構圖
echo -e "\n${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}         分離消費者架構已啟動${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Booking Service                   Ticketing Service"
echo "  ┌──────────────┐                 ┌──────────────────┐"
echo "  │              │                 │                  │"
echo "  │ Response     │◄──[response]────│                  │"
echo "  │ Consumer     │                 │                  │"
echo "  │ (PID:$BOOKING_PID)  │                 │ Request Consumer │"
echo "  │              │────[request]────►│ (PID:$TICKETING_PID)     │"
echo "  │              │                 │                  │"
echo "  └──────────────┘                 └──────────────────┘"
echo ""
echo -e "${YELLOW}監聽的 Topics:${NC}"
echo "  • ticketing-booking-request  (Ticketing 消費者)"
echo "  • ticketing-booking-response (Booking 消費者)"
echo ""
echo -e "${YELLOW}按 Ctrl+C 停止所有消費者${NC}"
echo ""

# 等待所有背景進程
wait