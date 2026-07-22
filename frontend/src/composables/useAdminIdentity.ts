import { shallowRef } from 'vue'
import { requestEnvelope } from '../api/http'
import type { AdminPermission, AdminRole, AdminUser } from '../types/system'

export function useAdminIdentity() {
  const users = shallowRef<AdminUser[]>([])
  const roles = shallowRef<AdminRole[]>([])
  const permissions = shallowRef<Record<string, AdminPermission[]>>({})
  const loading = shallowRef(false)
  const errorMessage = shallowRef('')

  async function loadUsersAndRoles() {
    loading.value = true
    errorMessage.value = ''
    try {
      const [userItems, roleItems] = await Promise.all([
        requestEnvelope<AdminUser[]>('/api/admin/users'), requestEnvelope<AdminRole[]>('/api/admin/roles'),
      ])
      users.value = userItems
      roles.value = roleItems
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '加载用户与角色失败'
    } finally { loading.value = false }
  }

  async function loadRolesAndPermissions() {
    loading.value = true
    errorMessage.value = ''
    try {
      const [roleItems, permissionItems] = await Promise.all([
        requestEnvelope<AdminRole[]>('/api/admin/roles'), requestEnvelope<Record<string, AdminPermission[]>>('/api/admin/permissions'),
      ])
      roles.value = roleItems
      permissions.value = permissionItems
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '加载角色与权限失败'
    } finally { loading.value = false }
  }

  async function saveUser(user: Partial<AdminUser> & { username?: string; password?: string; role_ids: number[] }) {
    const existing = user.id
    await requestEnvelope<AdminUser>(existing ? `/api/admin/users/${existing}` : '/api/admin/users', { method: existing ? 'PUT' : 'POST', body: JSON.stringify(user) })
    await loadUsersAndRoles()
  }

  async function updateUser(userId: number, payload: Partial<AdminUser>) {
    await requestEnvelope<AdminUser>(`/api/admin/users/${userId}`, { method: 'PUT', body: JSON.stringify(payload) })
    await loadUsersAndRoles()
  }

  async function removeUser(userId: number) {
    await requestEnvelope<null>(`/api/admin/users/${userId}`, { method: 'DELETE' })
    await loadUsersAndRoles()
  }

  async function saveRole(role: Partial<AdminRole> & { permission_ids: number[] }) {
    const existing = role.id
    await requestEnvelope<AdminRole>(existing ? `/api/admin/roles/${existing}` : '/api/admin/roles', { method: existing ? 'PUT' : 'POST', body: JSON.stringify(role) })
    await loadRolesAndPermissions()
  }

  async function removeRole(roleId: number) {
    await requestEnvelope<null>(`/api/admin/roles/${roleId}`, { method: 'DELETE' })
    await loadRolesAndPermissions()
  }

  return { users, roles, permissions, loading, errorMessage, loadUsersAndRoles, loadRolesAndPermissions, saveUser, updateUser, removeUser, saveRole, removeRole }
}
