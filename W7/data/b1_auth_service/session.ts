export interface SessionData {
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
