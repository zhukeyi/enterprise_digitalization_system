import axios from 'axios'

const client = axios.create({ baseURL: '/fde-api', timeout: 60000 })

export interface HROverview {
  total_employees: number
  active_count: number
  departments: { name: string; count: number }[]
  risk_distribution: { low: number; medium: number; high: number; critical: number }
  recent_hires: { id: string; name: string; department: string; position: string; hire_date: string }[]
}

export interface EmployeeSummary {
  employee_id: string
  name: string
  department: string
  position: string
  status: string
  risk_level: string
}

export interface DepartmentInfo {
  dept_id: string
  name: string
  head_count: number
  budget: number
}

export async function getOverview(): Promise<HROverview> {
  const { data } = await client.get<HROverview>('/api/hr/overview')
  return data
}

export async function getEmployees(dept?: string): Promise<EmployeeSummary[]> {
  const url = dept ? `/api/hr/employees?department=${dept}` : '/api/hr/employees'
  const { data } = await client.get<EmployeeSummary[]>(url)
  return data
}

export async function getEmployeeDetail(id: string): Promise<Record<string, any>> {
  const { data } = await client.get(`/api/hr/employees/${id}`)
  return data
}

export async function getDepartments(): Promise<DepartmentInfo[]> {
  const { data } = await client.get<DepartmentInfo[]>('/api/hr/departments')
  return data
}

export async function getRiskAssessment(id: string): Promise<Record<string, any>> {
  const { data } = await client.post(`/api/hr/risk/${id}`)
  return data
}

export async function getRedundancy(deptId: string): Promise<Record<string, any>> {
  const { data } = await client.post(`/api/hr/redundancy/${deptId}`)
  return data
}
