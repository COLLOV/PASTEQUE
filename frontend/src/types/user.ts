export interface CreateUserRequest {
  username: string
  password: string
}

export interface CreateUserResponse {
  username: string
  show_dashboard_charts?: boolean
}
