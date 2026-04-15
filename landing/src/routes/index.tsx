// landing/src/routes/index.tsx
import { createFileRoute } from '@tanstack/react-router'
import { HeroSection }    from '~/components/HeroSection'
import { LogoBand }       from '~/components/LogoBand'
import { HowItWorks }     from '~/components/HowItWorks'
import { StatsSection }   from '~/components/StatsSection'
import { MissionSection } from '~/components/MissionSection'
import { CTASection }     from '~/components/CTASection'

export const Route = createFileRoute('/')({
  component: HomePage,
})

function HomePage() {
  return (
    <>
      <HeroSection />
      <div className="section-divider"/>
      <LogoBand />
      <div className="section-divider"/>
      <HowItWorks />
      <StatsSection />
      <MissionSection />
      <CTASection />
    </>
  )
}
