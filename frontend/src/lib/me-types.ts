export type MeResponse = {
  id: number
  email: string
  roles: string[]
  display_name?: string | null
  given_name?: string | null
  family_name?: string | null
  preferred_username?: string | null
}
