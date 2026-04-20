// landing/src/routes/index.tsx — Landing v2
import { createFileRoute } from '@tanstack/react-router'
import { HeroSection }    from '~/components/HeroSection'
import { LogoBand }       from '~/components/LogoBand'
import { HowItWorks }     from '~/components/HowItWorks'
import { StatsSection }   from '~/components/StatsSection'
import { FeaturesSection } from '~/components/FeaturesSection'
import { MissionSection } from '~/components/MissionSection'
import { CTASection }     from '~/components/CTASection'

export const Route = createFileRoute('/')({
  component: HomePage,
})

function HomePage() {
  return (
    <>
      <HeroSection />
      <LogoBand />
      <HowItWorks />
      <StatsSection />
      <FeaturesSection />
      <MissionSection />
      <CTASection />
    </>
  )
}
