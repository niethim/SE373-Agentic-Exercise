"""Script tạo fixture dữ liệu cho Challenge B:
1. Dữ liệu B1: Mã nguồn service xác thực và session (auth.ts, session.ts, auth.test.ts)
2. Dữ liệu B2: 100 file log của hệ thống backend phân tán
"""

import os
import random
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
B1_DIR = BASE_DIR / "data" / "b1_auth_service"
B2_DIR = BASE_DIR / "data" / "b2_logs"


def generate_b1_fixtures():
    B1_DIR.mkdir(parents=True, exist_ok=True)

    auth_ts = """import { verifyToken, signRefreshToken, signAccessToken } from './jwt';
import { SessionStore } from './session';

export interface RefreshResponse {
  accessToken: string;
  refreshToken: string;
  tokenType: 'Bearer';
  expiresIn: number;
}

export class AuthService {
  constructor(private sessionStore: SessionStore) {}

  /**
   * Refresh token endpoint handler.
   * RÀNG BUỘC: Giữ backward compatibility cho API response format.
   * LỖI HIỆN TẠI: Race condition khi nhiều request refresh gửi đồng thời từ cùng 1 client.
   */
  async refreshToken(oldRefreshToken: string): Promise<RefreshResponse> {
    const payload = await verifyToken(oldRefreshToken);
    const session = await this.sessionStore.get(payload.sessionId);

    if (!session || session.refreshToken !== oldRefreshToken) {
      throw new Error('Invalid or already used refresh token');
    }

    // RACE CONDITION WINDOW: Giữa lúc đọc session và ghi đè session mới
    // Nếu 2 request cùng đọc session hợp lệ, request thứ 2 sẽ bị 401 khi revoke token cũ
    const newAccessToken = signAccessToken({ userId: payload.userId, sessionId: payload.sessionId });
    const newRefreshToken = signRefreshToken({ userId: payload.userId, sessionId: payload.sessionId });

    // Cập nhật session với refresh token mới
    await this.sessionStore.update(payload.sessionId, {
      refreshToken: newRefreshToken,
      updatedAt: Date.now()
    });

    return {
      accessToken: newAccessToken,
      refreshToken: newRefreshToken,
      tokenType: 'Bearer',
      expiresIn: 3600
    };
  }
}
"""

    session_ts = """export interface SessionData {
  userId: string;
  refreshToken: string;
  updatedAt: number;
}

export class SessionStore {
  private store = new Map<string, SessionData>();

  async get(sessionId: string): Promise<SessionData | null> {
    return this.store.get(sessionId) || null;
  }

  async update(sessionId: string, data: SessionData): Promise<void> {
    this.store.set(sessionId, data);
  }
}
"""

    auth_test_ts = """import { AuthService } from './auth';
import { SessionStore } from './session';

describe('AuthService Concurrency Test', () => {
  it('should handle concurrent refresh token requests without race condition', async () => {
    const sessionStore = new SessionStore();
    const authService = new AuthService(sessionStore);

    // Giả lập 5 requests refresh token đồng thời từ cùng một client session
    const sessionId = 'sess-12345';
    const initialRefreshToken = 'rt-init-001';
    await sessionStore.update(sessionId, { userId: 'u-1', refreshToken: initialRefreshToken, updatedAt: Date.now() });

    const promises = [
      authService.refreshToken(initialRefreshToken),
      authService.refreshToken(initialRefreshToken),
      authService.refreshToken(initialRefreshToken)
    ];

    const results = await Promise.allSettled(promises);
    const rejected = results.filter(r => r.status === 'rejected');
    
    // Yêu cầu: Không được throw race condition Error 'Invalid or already used refresh token'
    expect(rejected.length).toBe(0);
  });
});
"""

    (B1_DIR / "auth.ts").write_text(auth_ts, encoding="utf-8")
    (B1_DIR / "session.ts").write_text(session_ts, encoding="utf-8")
    (B1_DIR / "auth.test.ts").write_text(auth_test_ts, encoding="utf-8")
    print(f"[B1] Đã tạo 3 file source tại {B1_DIR}")


def generate_b2_fixtures():
    B2_DIR.mkdir(parents=True, exist_ok=True)

    # Các loại lỗi và tần suất mong đợi
    error_defs = [
        ("DatabaseConnectionTimeout", "ERROR: Connection timeout after 30000ms at DatabasePool.acquireConnection", 520),
        ("NullPointerException", "ERROR: NullPointerException in PaymentService.processTransaction line 142", 310),
        ("TokenExpiredException", "ERROR: JWT verification failed: TokenExpiredException at AuthGuard.canActivate", 215),
        ("RateLimitExceeded", "WARN: Rate limit threshold exceeded: 429 Too Many Requests for client IP", 140),
        ("DiskIOFailure", "FATAL: DiskIOFailure: write operation aborted on /var/log/storage/replica-0", 85)
    ]

    # Phân bổ lỗi vào 100 files
    file_errors = {i: [] for i in range(1, 101)}

    for err_name, err_sample, total_count in error_defs:
        for _ in range(total_count):
            chosen_file = random.randint(1, 100)
            file_errors[chosen_file].append((err_name, err_sample))

    normal_messages = [
        "INFO: Incoming HTTP GET /api/v1/health status=200 duration=2ms",
        "INFO: Worker thread pool initialized with 16 workers",
        "DEBUG: Cache hit for key user_session_payload",
        "INFO: Outgoing webhook dispatched successfully to payment-gateway",
        "DEBUG: Garbage collection completed in 14ms"
    ]

    total_generated_errors = 0
    for file_idx in range(1, 101):
        lines = []
        file_path = B2_DIR / f"service-{file_idx:03d}.log"

        # Xen kẽ log bình thường và log lỗi
        errors = file_errors[file_idx]
        total_generated_errors += len(errors)

        for line_num in range(1, 40):
            timestamp = f"2026-10-27T08:{random.randint(10, 59):02d}:{random.randint(10, 59):02d}.{random.randint(100, 999):03d}Z"
            if errors and random.random() < 0.35:
                err_name, sample = errors.pop(0)
                lines.append(f"[{timestamp}] [worker-{file_idx}] {sample}")
            else:
                lines.append(f"[{timestamp}] [worker-{file_idx}] {random.choice(normal_messages)}")

        # Đẩy hết lỗi còn lại nếu có
        for err_name, sample in errors:
            timestamp = f"2026-10-27T08:59:59.{random.randint(100, 999):03d}Z"
            lines.append(f"[{timestamp}] [worker-{file_idx}] {sample}")

        file_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"[B2] Đã sinh 100 file log tại {B2_DIR} (Tổng số lỗi chuẩn: {total_generated_errors})")


if __name__ == "__main__":
    generate_b1_fixtures()
    generate_b2_fixtures()
