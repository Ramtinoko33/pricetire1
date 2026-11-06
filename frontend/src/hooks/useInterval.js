import { useEffect, useRef } from 'react';

// Executa `callback` a cada `delay` ms enquanto o componente estiver montado.
// `delay = null` pausa. O callback mais recente é sempre usado (sem reiniciar o timer).
export function useInterval(callback, delay) {
  const saved = useRef(callback);

  useEffect(() => {
    saved.current = callback;
  }, [callback]);

  useEffect(() => {
    if (delay === null || delay === undefined) return undefined;
    const id = setInterval(() => saved.current?.(), delay);
    return () => clearInterval(id);
  }, [delay]);
}
