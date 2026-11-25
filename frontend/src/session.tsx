import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

type Session = { memberId: number | null; setMemberId: (id: number | null) => void }
const Ctx = createContext<Session>({ memberId: null, setMemberId: () => {} })

export function SessionProvider({ children }: { children: ReactNode }) {
  const [memberId, setMemberId] = useState<number | null>(() => {
    const v = localStorage.getItem('mn.memberId')
    return v ? Number(v) : null
  })
  useEffect(() => {
    if (memberId == null) localStorage.removeItem('mn.memberId')
    else localStorage.setItem('mn.memberId', String(memberId))
  }, [memberId])
  return <Ctx.Provider value={{ memberId, setMemberId }}>{children}</Ctx.Provider>
}

export const useSession = () => useContext(Ctx)
