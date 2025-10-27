export interface CreateUserRequest {
  username: string
  password: string
}

export interface CreateUserResponse {
  username: string
}

export interface UserWithPermissionsResponse {
  username: string
  is_active: boolean
  is_admin: boolean
  created_at: string
  allowed_tables: string[]
}

export interface UserPermissionsOverviewResponse {
  tables: string[]
  users: UserWithPermissionsResponse[]
}

export interface UpdateUserPermissionsRequest {
  allowed_tables: string[]
}
