import api from './axios'

export const healthApi = {
  getHealth: async (): Promise<any> => {
    const res = await api.get('/health')
    return res.data
  },
  getReconciliation: async (): Promise<any> => {
    const res = await api.get('/trade/reconciliation')
    return res.data
  },
}
