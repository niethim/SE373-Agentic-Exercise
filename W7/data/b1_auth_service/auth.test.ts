import { AuthService } from './auth';
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
