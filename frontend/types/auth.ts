export interface LoginRequest {
  username: string;
  password: string;
}

export interface UserProfile {
  id: number;
  name: string;
  username: string;
  email: string | null;
  mobile: string | null;
  department: string | null;
  wechat_user_id: string | null;
  oa_admin_id?: number | null;
  role: "ADMIN" | "EXECUTIVE" | "PROJECT_OWNER" | "MEMBER";
  status: "ACTIVE" | "INACTIVE";
  created_at: string;
  updated_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserProfile;
}
