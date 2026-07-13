// Tweaks app for landing.html — theme (dark/light) control.
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{ "theme": "dark" }/*EDITMODE-END*/;

function VxTweaks() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  React.useEffect(() => {
    document.documentElement.setAttribute('data-theme', t.theme);
  }, [t.theme]);
  return (
    <TweaksPanel>
      <TweakSection label="Appearance" />
      <TweakRadio label="Theme" value={t.theme} options={['dark', 'light']} onChange={(v) => setTweak('theme', v)} />
    </TweaksPanel>
  );
}

ReactDOM.createRoot(document.getElementById('vx-tweaks')).render(<VxTweaks />);
