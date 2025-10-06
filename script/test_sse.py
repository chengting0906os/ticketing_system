#!/usr/bin/env python3
"""
SSE 測試腳本
測試座位狀態即時推送功能
"""

import asyncio
import httpx


async def test_sse_stream():
    """測試 SSE 串流"""
    url = 'http://localhost:8000/api/reservation/1/sections/A/subsection/1/seats/stream'

    print(f'🔗 Connecting to SSE stream: {url}')
    print('=' * 80)

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream('GET', url) as response:
            print(f'✅ Connected! Status: {response.status_code}')
            print(f'📡 Headers: {dict(response.headers)}')
            print('=' * 80)
            print('📊 Receiving seat updates (Ctrl+C to stop)...')
            print('=' * 80)

            event_count = 0
            async for line in response.aiter_lines():
                if line.startswith('data: '):
                    event_count += 1
                    data = line[6:]  # Remove 'data: ' prefix

                    # 只顯示前幾個事件的完整資料
                    if event_count <= 3:
                        print(f'\n📦 Event #{event_count}:')
                        print(data)
                    else:
                        # 之後只顯示摘要
                        import json

                        try:
                            parsed = json.loads(data)
                            if 'error' in parsed:
                                print(f'\n❌ Event #{event_count}: ERROR - {parsed["error"]}')
                            else:
                                stats = f'available={parsed.get("available", 0)}, reserved={parsed.get("reserved", 0)}, sold={parsed.get("sold", 0)}'
                                print(
                                    f'✅ Event #{event_count}: {parsed.get("section_id", "N/A")} - {stats}'
                                )
                        except json.JSONDecodeError:
                            print(f'⚠️  Event #{event_count}: Invalid JSON')

                    # 測試 10 個事件後停止
                    if event_count >= 10:
                        print('\n' + '=' * 80)
                        print(f'🎉 Test completed! Received {event_count} events')
                        break


if __name__ == '__main__':
    try:
        asyncio.run(test_sse_stream())
    except KeyboardInterrupt:
        print('\n🛑 Test stopped by user')
    except Exception as e:
        print(f'\n❌ Error: {e}')
