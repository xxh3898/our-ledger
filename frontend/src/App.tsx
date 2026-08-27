import './App.css'

const foundationItems = [
  {
    label: 'Backend',
    value: 'Spring Boot 4.1',
    detail: 'Java 25 · PostgreSQL 18 · Flyway',
  },
  {
    label: 'Frontend',
    value: 'React 19.2',
    detail: 'TypeScript 6 · Vite 8',
  },
  {
    label: '검증',
    value: 'Foundation',
    detail: 'Unit · Integration · Hosted CI',
  },
]

function App() {
  return (
    <main className="app-shell">
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">둘이 함께 쌓는 하나의 기록</p>
        <h1 id="page-title">우리의 장부</h1>
        <p className="hero-copy">
          개인 소비와 공동 목표를 한눈에 관리할 수 있도록 기본 실행 환경을 준비했습니다.
        </p>
        <div className="status" role="status">
          <span className="status-dot" aria-hidden="true" />
          Foundation 준비 완료
        </div>
      </section>

      <section className="foundation" aria-labelledby="foundation-title">
        <div>
          <p className="section-kicker">Slice 0</p>
          <h2 id="foundation-title">안정적인 시작점</h2>
        </div>
        <div className="foundation-grid">
          {foundationItems.map((item) => (
            <article className="foundation-card" key={item.label}>
              <p>{item.label}</p>
              <strong>{item.value}</strong>
              <span>{item.detail}</span>
            </article>
          ))}
        </div>
      </section>
    </main>
  )
}

export default App
