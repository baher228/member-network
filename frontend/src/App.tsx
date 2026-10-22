import { BrowserRouter, NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { SessionProvider } from './session'
import { HealthBar, MemberPicker } from './components/chrome'
import Questionnaire from './pages/Questionnaire'
import ForYou from './pages/ForYou'
import Intros from './pages/Intros'
import Speakers from './pages/Speakers'
import Members from './pages/Members'
import Evaluation from './pages/Evaluation'

const nav = [
  ['/join', 'Questionnaire'],
  ['/for-you', 'For you'],
  ['/intros', 'Intros'],
  ['/speakers', 'Speakers'],
  ['/members', 'Members'],
  ['/eval', 'Evaluation'],
] as const

export default function App() {
  return (
    <SessionProvider>
      <BrowserRouter>
        <div className="min-h-screen">
          <header className="sticky top-0 z-20 border-b border-line bg-bg/90 backdrop-blur">
            <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-fg" />
                <span className="text-sm font-medium tracking-tight">Member Network</span>
                <span className="label hidden sm:inline">· Know your members</span>
              </div>
              <nav className="order-3 -mx-1 flex w-full gap-1 overflow-x-auto sm:order-none sm:w-auto">
                {nav.map(([to, label]) => (
                  <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                      `whitespace-nowrap rounded-md px-2.5 py-1 text-sm transition-colors duration-150 ${isActive ? 'bg-[#1c1c1c] text-fg' : 'text-muted hover:bg-hover hover:text-fg'}`
                    }
                  >
                    {label}
                  </NavLink>
                ))}
              </nav>
              <div className="ml-auto"><MemberPicker /></div>
            </div>
          </header>
          <HealthBar />
          <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
            <Routes>
              <Route path="/" element={<Navigate to="/for-you" replace />} />
              <Route path="/join" element={<Questionnaire />} />
              <Route path="/for-you" element={<ForYou />} />
              <Route path="/intros" element={<Intros />} />
              <Route path="/speakers" element={<Speakers />} />
              <Route path="/members" element={<Members />} />
              <Route path="/eval" element={<Evaluation />} />
              <Route path="*" element={<Navigate to="/for-you" replace />} />
            </Routes>
          </main>
          <footer className="mx-auto max-w-6xl px-4 pb-10 sm:px-6">
            <div className="label border-t border-line pt-4">Open source · MIT · Records marked “Demo data” are synthetic</div>
          </footer>
        </div>
      </BrowserRouter>
    </SessionProvider>
  )
}
