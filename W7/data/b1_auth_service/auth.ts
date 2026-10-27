import { verifyToken, signRefreshToken, signAccessToken } from './jwt';
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
